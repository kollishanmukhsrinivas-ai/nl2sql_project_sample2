"""
Natural-language question -> SQL, grounded in the live database schema.
"""
import re
from langchain_core.prompts import ChatPromptTemplate

from app.llm.llm_service import get_llm
from app.sql.validator import validate_sql, SQLValidationError
from app.db.database_service import explain_sql, DatabaseConnectionError

SYSTEM_PROMPT = """You are an expert SQL generator for a {dialect} database.
Given a database schema and a user question, generate a single valid,
read-only SELECT SQL query that answers the question as fully as asked.
Do not simplify or drop parts of a multi-part question - address every
condition and comparison the question describes.

Basic rules:
- Only use the tables and columns provided in the schema below. Never invent columns or tables.
- Use explicit JOINs (with ON conditions) when the question requires data from multiple tables.
- Output ONLY the raw SQL query. No explanation, no markdown code fences, no <think> tags, no preamble.
- The query must be a single statement (no semicolons, no multiple statements).
- Never generate INSERT, UPDATE, DELETE, DROP, ALTER, or TRUNCATE statements.

Column matching rules (free-text vs categorical):
- Free-text / descriptive columns (e.g. reason, comments, notes, description,
  address, remarks) NEVER use exact match (=). Always use LIKE '%keyword%'
  with the core keyword extracted from the question, ignoring filler words
  like "on purpose for", "reason of", "because of".
- Categorical / enum columns (e.g. status, leave_type, department, gender)
  DO use exact match (=) with one of the known values from the schema.
- If a question describes a purpose, activity, or free-text concept (e.g.
  "vacation", "personal reasons", "medical") rather than a known category
  value, search the free-text column with LIKE, not the categorical column.

Column location rules (critical - the most frequent model errors happen here):
- employees has NO single `name` column - always use first_name and
  last_name separately, or CONCAT(first_name, ' ', last_name) if a full
  name is needed in the output.
- salaries table ONLY contains: base_salary, bonus, allowance, salary_grade,
  effective_from, effective_to. Nothing else lives here.
- old_salary, new_salary, promotion_date, old_job_id, new_job_id, old_department_id,
  new_department_id live ONLY in `promotions`, never in `salaries` or `employees`.
- minimum_salary, maximum_salary, job_level, job_title live ONLY in `jobs`,
  never in `salaries` or `employees`.
- The `training` table has NO emp_id column - to link training to an
  employee, JOIN through `employee_training` (emp_id, training_id).
- overall_rating, productivity_rating, quality_rating, teamwork_rating,
  communication_rating, leadership_rating, review_date live ONLY in
  `performance_reviews`.
- Never join a department_id column to an emp_id column, or vice versa -
  they are never the same key. Only join columns of the same kind
  (id-to-id, emp_id-to-emp_id, department_id-to-department_id, etc).
- When a question needs current manager/department/job (not history), use
  the row in `employment_history` where end_date IS NULL, not just any row.

MySQL syntax rules:
- Every derived/sub-query table used in FROM must have an alias:
  FROM (SELECT ...) AS some_alias
- Never use reserved words (rank, rows, row_number, order, group) as an
  unquoted column alias - quote them with backticks or rename them
  (e.g. use `salary_rank` instead of `rank`).
- A window function's result (e.g. RANK() AS salary_rank) CANNOT be
  filtered in the same-level WHERE clause. Always wrap it in an outer
  subquery first: SELECT * FROM (SELECT ..., RANK() OVER (...) AS
  salary_rank FROM ...) AS ranked WHERE ranked.salary_rank <= 2
- When joining 3 or more tables, or self-joining the same table twice
  (e.g. employees AS e JOIN employees AS m), ALWAYS qualify every single
  column in SELECT/WHERE/ON with its table alias - never a bare column
  name, to avoid ambiguous column errors.

Superlative rule:
- Questions like "the employee/department who has the most/least/
  highest/lowest X" require ORDER BY X DESC (or ASC) LIMIT 1 - never
  return all rows when the question asks for a single top/bottom result.

Examples:
Q: "employees who took leave for vacation"
SQL: SELECT emp_id, reason FROM leaves WHERE reason LIKE '%vacation%'

Q: "who is currently on sick leave"
SQL: SELECT emp_id FROM leaves WHERE leave_type = 'Sick'

Q: "employees whose leave request is pending"
SQL: SELECT emp_id FROM leaves WHERE status = 'Pending'

Q: "employee with the second-highest base_salary in each department"
SQL: SELECT e1.emp_id, e1.department_id, s1.base_salary
     FROM employees e1
     JOIN salaries s1 ON e1.emp_id = s1.emp_id
     WHERE (
       SELECT COUNT(*) FROM employees e2
       JOIN salaries s2 ON e2.emp_id = s2.emp_id
       WHERE e2.department_id = e1.department_id
         AND s2.base_salary > s1.base_salary
     ) = 1

Q: "employees promoted, and their salary increase compared to their performance rating after the promotion"
SQL: SELECT p.emp_id, e.first_name, e.last_name, p.old_salary, p.new_salary,
            (p.new_salary - p.old_salary) AS salary_increase,
            pr.overall_rating
     FROM promotions p
     JOIN employees e ON p.emp_id = e.emp_id
     JOIN performance_reviews pr ON p.emp_id = pr.emp_id
     WHERE pr.review_date > p.promotion_date
     ORDER BY salary_increase DESC

Schema:
{schema}
"""

REPAIR_PROMPT = """You are an expert SQL generator for a {dialect} database.
Your previous SQL query failed with an error. Fix it using the schema below.

Original question: {question}

Your previous (incorrect) SQL:
{previous_sql}

Database error:
{error}

Schema:
{schema}

Output ONLY the corrected raw SQL query. No explanation, no markdown fences.
"""

prompt_template = ChatPromptTemplate.from_messages([
    ("system", SYSTEM_PROMPT),
    ("user", "Question: {question}\n\nSQL Query:"),
])

repair_prompt_template = ChatPromptTemplate.from_messages([
    ("system", REPAIR_PROMPT),
])


def _extract_text(response) -> str:
    """Handles both plain string LLM responses (Ollama) and message objects (chat models)."""
    return response.content if hasattr(response, "content") else str(response)


def clean_sql_output(raw: str) -> str:
    text = raw.strip()
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    text = re.sub(r"```sql|```", "", text)
    return text.strip()


def fix_common_alias_mistakes(sql: str) -> str:
    """
    Mechanically corrects the model's most persistent mistakes that
    prompt rules alone don't reliably prevent on a small model:
    - e.name (doesn't exist) -> CONCAT(e.first_name, ' ', e.last_name)
    - bare `rank` as an alias/column (MySQL reserved word) -> `salary_rank`
    """
    for match in re.finditer(r"\bemployees\s+(?:AS\s+)?(\w+)\b", sql, re.IGNORECASE):
        alias = match.group(1)
        sql = re.sub(
            rf"\b{re.escape(alias)}\.name\b",
            f"CONCAT({alias}.first_name, ' ', {alias}.last_name)",
            sql,
        )
    sql = re.sub(r"\bAS\s+rank\b", "AS salary_rank", sql, flags=re.IGNORECASE)
    sql = re.sub(r"\.rank\b(?!_)", ".salary_rank", sql)
    sql = re.sub(r"\bWHERE\s+rank\b", "WHERE salary_rank", sql, flags=re.IGNORECASE)
    return sql


def generate_sql(question: str, schema: str, dialect: str = "SQL") -> str:
    llm = get_llm()
    chain = prompt_template | llm
    raw_response = chain.invoke({"schema": schema, "question": question, "dialect": dialect})
    sql = clean_sql_output(_extract_text(raw_response))
    return fix_common_alias_mistakes(sql)


def generate_sql_with_retry(question: str, schema: str, dialect: str = "SQL", max_retries: int = 1) -> str:
    """
    Generates SQL, then validates + EXPLAINs it against the real DB.
    If it fails, feeds the exact error back to the model to self-correct,
    up to max_retries times. Returns the best attempt either way.
    """
    llm = get_llm()
    sql = generate_sql(question, schema, dialect)

    for _ in range(max_retries):
        try:
            sql = validate_sql(sql)
            explain_sql(sql)
            return sql
        except (SQLValidationError, DatabaseConnectionError) as exc:
            repair_chain = repair_prompt_template | llm
            raw = repair_chain.invoke({
                "schema": schema,
                "question": question,
                "dialect": dialect,
                "previous_sql": sql,
                "error": str(exc),
            })
            sql = fix_common_alias_mistakes(clean_sql_output(_extract_text(raw)))

    return sql
