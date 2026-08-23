"""
Automated test runner for the NL2SQL pipeline.
"""
import time
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
        "top 3 highest paid employees",
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
}


def run_tests():
    total = 0
    passed = 0
    failures = []

    for category, questions in QUESTIONS.items():
        print(f"\n=== {category} ===")
        for q in questions:
            total += 1
            start = time.time()
            result = get_data_from_database(q)
            elapsed = time.time() - start

            if result.success:
                passed += 1
                print(f"  [PASS] ({elapsed:.1f}s) {q}")
            else:
                failures.append((category, q, result.error, result.sql))
                print(f"  [FAIL] ({elapsed:.1f}s) {q}")
                print(f"         Error: {result.error}")
                if result.sql:
                    print(f"         SQL: {result.sql}")

    print(f"\n{'='*60}")
    print(f"RESULT: {passed}/{total} passed ({passed/total*100:.0f}%)")
    print(f"{'='*60}")

    if failures:
        print("\nFAILED QUESTIONS SUMMARY:")
        for category, q, error, sql in failures:
            print(f"\n[{category}] {q}")
            print(f"  Error: {error}")
            if sql:
                print(f"  SQL: {sql}")


if __name__ == "__main__":
    run_tests()
