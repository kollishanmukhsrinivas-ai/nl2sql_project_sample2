"""
Automated test runner for the NL2SQL pipeline.

Usage:
    uv run python test_questions.py                # full run, all categories
    uv run python test_questions.py --quick         # 1 question per category (fast sanity check)
    uv run python test_questions.py --category ranking   # only that category
    uv run python test_questions.py --no-retry       # skip repair/retry on failure (faster, less accurate)
    uv run python test_questions.py --quick --no-retry   # fastest possible smoke test

Correctness checking:
    Each question can be a plain string (checked only for row_count > 0, a weak
    "did it silently return nothing" check) OR a dict with an "expected" field:

        {"q": "top 3 highest paid employees", "expected": {"row_count": 3}}
        {"q": "employees hired in 2099", "expected": {"row_count": 0}}
        {"q": "count of departments", "expected": {"min_rows": 1, "max_rows": 1}}

    Fill these in over time by running once, eyeballing the printed row count,
    and locking it in as the known-good baseline. Until you do, every question
    just gets the weak row_count > 0 check (except ones you've marked as
    expecting 0 rows).
"""
import argparse
import json
import time
from datetime import datetime
from pathlib import Path

from app.pipeline import get_data_from_database

QUESTIONS = {
    "basic_categorical": [
        "who is currently on sick leave",
        "which leave requests are pending",
        "list all approved leave requests",
    ],
    "free_text_like": [
        "employees who took leave for vacation",
        "who took leave due to illness",
    ],
    "aggregation": [
        "average base salary by department",
        "count of leave requests by status",
        "total bonus paid per salary grade",
    ],
    "single_hop_join": [
        "which department does employee 5 belong to",
        "show base salary along with employee name",
    ],
    "multi_hop_join": [
        "average base salary per department",
        "which employees have pending leave requests along with their department",
    ],
    "ranking": [
        {"q": "top 3 highest paid employees", "expected": {"row_count": 3}},
        "employee with the second-highest base_salary in each department",
        "Rank employees within each department by base_salary and show only rank 1 and rank 2",
    ],
    "date_logic": [
        "employees hired in the last 5 years",
        "leave requests submitted more than 10 days before the start date",
    ],
    "complex_multi_table": [
        "which employees have received a promotion and subsequently had a performance review, and what was their salary increase compared to their performance rating",
        "For each employee, determine whether their current salary is consistent with their current job's minimum and maximum salary range",
        "Find the department where the ratio of pending to approved leave requests is highest",
    ],
    "hallucination_trap": [
        "top 5 customers by total order amount",
        "employees by performance rating category that does not exist",
    ],
    # New: edge cases that a "did it execute without error" check alone would miss.
    "edge_cases": [
        # Valid query, but should legitimately return zero rows -- tests that
        # empty results aren't confused with failures.
        {"q": "employees hired in the year 2099", "expected": {"row_count": 0}},
        # Vague/ambiguous -- there's no single correct SQL here, so this is
        # really testing that the pipeline doesn't crash on it. Read the SQL
        # by hand rather than trusting PASS/FAIL alone.
        "show me the data",
        # Typos / casual phrasing -- real users don't type cleanly.
        "wat employes r on sick leave",
        # NULL handling -- classic source of silent SQL bugs.
        "employees without a manager assigned",
        # SQL-injection-style input -- must be treated as a literal question,
        # never as SQL to splice in. This is a safety check, not an
        # LLM-prompt-injection test.
        "employees'; DROP TABLE employees;--",
    ],
}


def parse_args():
    parser = argparse.ArgumentParser(description="NL2SQL pipeline test runner")
    parser.add_argument(
        "--quick", action="store_true",
        help="Run only the first question from each category (fast sanity check)",
    )
    parser.add_argument(
        "--category", type=str, default=None,
        help="Run only the given category (e.g. --category ranking)",
    )
    parser.add_argument(
        "--no-retry", action="store_true",
        help="Skip the repair/retry step on failure (roughly halves worst-case time, may lower pass rate)",
    )
    parser.add_argument(
        "--no-save", action="store_true",
        help="Don't write a JSON results file",
    )
    return parser.parse_args()


def build_question_set(args):
    if args.category:
        if args.category not in QUESTIONS:
            valid = ", ".join(QUESTIONS.keys())
            raise SystemExit(f"Unknown category '{args.category}'. Valid: {valid}")
        questions = {args.category: QUESTIONS[args.category]}
    else:
        questions = QUESTIONS

    if args.quick:
        questions = {cat: qs[:1] for cat, qs in questions.items()}

    return questions


def normalize(item):
    """Accept either a plain string or a {"q": ..., "expected": {...}} dict."""
    if isinstance(item, str):
        return item, {}
    return item["q"], item.get("expected", {})


def check_correctness(result, expected):
    """
    Returns (ok, reason). If no expected values are given, falls back to a
    weak row_count > 0 check -- catches "silently returned nothing" without
    requiring every question to have hand-verified expected values.
    """
    row_count = len(result.rows) if result.rows is not None else 0

    if "row_count" in expected:
        want = expected["row_count"]
        if row_count != want:
            return False, f"expected exactly {want} rows, got {row_count}"
        return True, None

    if "min_rows" in expected or "max_rows" in expected:
        lo = expected.get("min_rows", 0)
        hi = expected.get("max_rows", float("inf"))
        if not (lo <= row_count <= hi):
            return False, f"expected {lo}-{hi} rows, got {row_count}"
        return True, None

    # No expected value supplied -- weak default check.
    if row_count == 0:
        return False, "weak check: query succeeded but returned 0 rows (no 'expected' set for this question, so this may be a false alarm -- verify by hand)"
    return True, None


def run_tests(args):
    questions = build_question_set(args)

    total = 0
    passed = 0
    failures = []
    category_stats = {}  # cat -> [passed, total]
    run_start = time.time()

    call_kwargs = {}
    if args.no_retry:
        call_kwargs["max_retries"] = 0

    for category, items in questions.items():
        print(f"\n=== {category} ===")
        category_stats.setdefault(category, [0, 0])

        for item in items:
            q, expected = normalize(item)
            total += 1
            category_stats[category][1] += 1
            start = time.time()
            result = get_data_from_database(q, **call_kwargs)
            elapsed = time.time() - start

            if not result.success:
                failures.append({
                    "category": category,
                    "question": q,
                    "error": result.error,
                    "sql": result.sql,
                    "elapsed": round(elapsed, 1),
                })
                print(f"  [FAIL] ({elapsed:.1f}s) {q}")
                print(f"         Error: {result.error}")
                if result.sql:
                    print(f"         SQL: {result.sql}")
            else:
                ok, reason = check_correctness(result, expected)
                row_count = len(result.rows) if result.rows is not None else 0
                if ok:
                    passed += 1
                    category_stats[category][0] += 1
                    print(f"  [PASS] ({elapsed:.1f}s) {q}  [{row_count} rows]")
                else:
                    failures.append({
                        "category": category,
                        "question": q,
                        "error": f"correctness check failed: {reason}",
                        "sql": result.sql,
                        "elapsed": round(elapsed, 1),
                    })
                    print(f"  [FAIL] ({elapsed:.1f}s) {q}  [{row_count} rows]")
                    print(f"         Correctness: {reason}")
                    if result.sql:
                        print(f"         SQL: {result.sql}")

            # running total, so a Ctrl+C mid-run still tells you something
            print(f"         running: {passed}/{total} passed")

    total_elapsed = time.time() - run_start

    print(f"\n{'='*60}")
    print(f"RESULT: {passed}/{total} passed ({passed/total*100:.0f}%)")
    print(f"Total time: {total_elapsed:.1f}s  |  Avg/question: {total_elapsed/total:.1f}s")
    print(f"{'='*60}")

    print("\nPER-CATEGORY BREAKDOWN:")
    for cat, (cat_passed, cat_total) in category_stats.items():
        print(f"  {cat:22s} {cat_passed}/{cat_total}")

    if failures:
        print("\nFAILED QUESTIONS SUMMARY:")
        for f in failures:
            print(f"\n[{f['category']}] {f['question']}")
            print(f"  Error: {f['error']}")
            if f["sql"]:
                print(f"  SQL: {f['sql']}")

    if not args.no_save:
        save_results(passed, total, total_elapsed, category_stats, failures, args)

    return passed, total


def save_results(passed, total, total_elapsed, category_stats, failures, args):
    out_dir = Path("test_results")
    out_dir.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = out_dir / f"results_{timestamp}.json"

    payload = {
        "timestamp": timestamp,
        "passed": passed,
        "total": total,
        "pass_rate": round(passed / total * 100, 1) if total else 0,
        "total_elapsed_sec": round(total_elapsed, 1),
        "avg_elapsed_sec": round(total_elapsed / total, 1) if total else 0,
        "flags": {
            "quick": args.quick,
            "category": args.category,
            "no_retry": args.no_retry,
        },
        "category_stats": {
            cat: {"passed": p, "total": t} for cat, (p, t) in category_stats.items()
        },
        "failures": failures,
    }

    out_path.write_text(json.dumps(payload, indent=2))
    print(f"\nResults saved to {out_path}")
    print("Compare against previous runs in test_results/ to see if changes helped.")


if __name__ == "__main__":
    run_tests(parse_args())
