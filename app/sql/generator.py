"""

Natural-language question -> SQL, grounded in the live database schema.

Column-location rules and mechanical post-processing fixes are derived
fresh from whatever schema is actually connected (see schema_service.py
helpers), rather than hardcoded for one specific database - so this
keeps working correctly even if tables/columns get renamed, added, or
restructured, as long as the overall data is still employee/HR-shaped.
"""
import re
from langchain_core.prompts import ChatPromptTemplate

from app.llm.llm_service import get_llm
from app.sql.validator import validate_sql, SQLValidationError
from app.db.database_service import explain_sql, DatabaseConnectionError
from app.db.schema_service import get_exclusive_columns, get_composite_name_tables

BASE_SYSTEM_PROMPT = """You are an expert SQL generator for a {dialect} database.
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
- If a question describes a purpose, activity, or free-text concept rather
  than a known category value, search the free-text column with LIKE.
- leaves table has NO department_id - to filter leave requests by
  department, JOIN leaves to employees first, then employees to
  departments.
- salaries table has NO department_id - to rank/group salaries by
  department, JOIN salaries to employees first.
- "illness" as a search term is a free-text concept, not a leave_type
  value - search reason with LIKE, never leave_type = 'Illness'.
- Never join two ID columns that have different names unless the
  schema explicitly shows a foreign key between them. For example,
  job_id and emp_id are never the same key, department_id and emp_id
  are never the same key - only join columns where the schema's FK
  annotation explicitly connects them.
- When a question mentions a value together with words from its own
  column name (e.g. "Annual leave" when the column is leave_type),
  match only the distinctive part of the value (e.g. 'Annual'), not
  the full phrase including the column's own name.

{dynamic_column_rules}

MySQL syntax rules:
- Every derived/sub-query table used in FROM must have an alias:
  FROM (SELECT ...) AS some_alias
- Never use reserved words (rank, rows, row_number, order, group) as an
  unquoted column alias - quote them with backticks or rename them
  (e.g. use `salary_rank` instead of `rank`).
- Use MySQL's LIMIT n syntax, never SQL Server's TOP n syntax.
- A window function's result (e.g. RANK() AS salary_rank) CANNOT be
  filtered in the same-level WHERE clause. Always wrap it in an outer
  subquery first: SELECT * FROM (SELECT ..., RANK() OVER (...) AS
  salary_rank FROM ...) AS ranked WHERE ranked.salary_rank <= 2
- When joining 3 or more tables, or self-joining the same table twice,
  ALWAYS qualify every single column in SELECT/WHERE/ON with its table
  alias - never a bare column name, to avoid ambiguous column errors.

Superlative rule:
- Questions like "the employee/department who has the most/least/
  highest/lowest X" require ORDER BY X DESC (or ASC) LIMIT 1 - never
  return all rows when the question asks for a single top/bottom result.

Examples:
Q: "employees who took leave for vacation"
SQL: SELECT emp_id, reason FROM leaves WHERE reason LIKE '%vacation%'

Q: "who is currently on sick leave"
SQL: SELECT emp_id FROM leaves WHERE leave_type = 'Sick'

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

repair_prompt_template = ChatPromptTemplate.from_messages([
    ("system", REPAIR_PROMPT),
])


def _build_dynamic_column_rules(schema_text: str) -> str:
    """
    Auto-derives 'this column only lives in this table' rules from
    whatever schema is currently connected, instead of hardcoding them
    for one specific database. Only includes a rule if that column
    actually appears in the (possibly filtered) schema text being sent
    for this question.
    """
    try:
        exclusive = get_exclusive_columns()
    except Exception:
        return ""

    skip = {"id", "created_at", "updated_at", "status", "reason", "comments", "description"}
    lines = []
    for col, table in exclusive.items():
        if col in skip:
            continue
        if col in schema_text:
            lines.append(f"- `{col}` lives ONLY in `{table}`.")

    if not lines:
        return ""

    return "Column location rules (auto-derived from the current schema):\n" + "\n".join(lines)


def _build_prompt_template(schema: str) -> ChatPromptTemplate:
    dynamic_rules = _build_dynamic_column_rules(schema)
    filled = BASE_SYSTEM_PROMPT.replace("{dynamic_column_rules}", dynamic_rules)
    return ChatPromptTemplate.from_messages([
        ("system", filled),
        ("user", "Question: {question}\n\nSQL Query:"),
    ])


def _extract_text(response) -> str:
    """Handles both plain string LLM responses (Ollama) and message objects (chat models)."""
    return response.content if hasattr(response, "content") else str(response)


def clean_sql_output(raw: str) -> str:
    text = raw.strip()
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    text = re.sub(r"```sql|```", "", text)
    return text.strip()


def extract_sql_statement(text: str) -> str:
    """
    Pulls out just the SQL statement from model output that may be
    wrapped in explanatory prose (increasingly common as the prompt
    has grown longer - the model sometimes stops following the
    "output ONLY SQL" instruction). Finds the first SELECT and cuts
    off at the next paragraph break or semicolon, discarding any
    explanation before or after.
    """
    match = re.search(r"SELECT\b", text, re.IGNORECASE)
    if not match:
        return text.strip()

    remainder = text[match.start():]

    para_match = re.search(r"\n\s*\n", remainder)
    if para_match:
        remainder = remainder[:para_match.start()]

    if ";" in remainder:
        remainder = remainder.split(";")[0]

    return remainder.strip()


def fix_common_alias_mistakes(sql: str) -> str:
    """
    Mechanically corrects the model's most persistent mistakes:
    - a combined `.name` column on a table that only has separate
      first/last name columns (derived fresh from the live schema)
    - bare `rank` used as an alias/column (MySQL reserved word)
    - SQL Server's `SELECT TOP n` syntax instead of MySQL's `LIMIT n`
    """
    try:
        composite_tables = get_composite_name_tables()
    except Exception:
        composite_tables = {}

    for table_name, (first_col, last_col) in composite_tables.items():
        for match in re.finditer(rf"\b{re.escape(table_name)}\s+(?:AS\s+)?(\w+)\b", sql, re.IGNORECASE):
            alias = match.group(1)
            sql = re.sub(
                rf"\b{re.escape(alias)}\.name\b",
                f"CONCAT({alias}.{first_col}, ' ', {alias}.{last_col})",
                sql,
            )

    sql = re.sub(r"\bAS\s+rank\b", "AS salary_rank", sql, flags=re.IGNORECASE)
    sql = re.sub(r"\.rank\b(?!_)", ".salary_rank", sql)
    sql = re.sub(r"\bWHERE\s+rank\b", "WHERE salary_rank", sql, flags=re.IGNORECASE)

    top_match = re.match(r"^\s*SELECT\s+TOP\s+(\d+)\s+(.*)", sql, re.IGNORECASE | re.DOTALL)
    if top_match:
        limit_n, rest = top_match.groups()
        sql = f"SELECT {rest.strip()} LIMIT {limit_n}"

    return sql


def fix_hallucinated_column_names(sql: str) -> str:
    """
    If the model references <alias>.<col> where <col> doesn't exist
    anywhere, but a very similar real column name (e.g. 'salary' vs
    'base_salary') is exclusive to a table that's ALREADY joined in
    this query under some alias, rewrite the reference to point at
    the correct alias and column. Only fixes cases where the owning
    table is already present in the query - it does not insert
    missing tables (that's a structural fix, not a naming one).
    """
    try:
        exclusive = get_exclusive_columns()
    except Exception:
        return sql

    table_alias_in_query = {}
    for tname in set(exclusive.values()):
        m = re.search(rf"\b{re.escape(tname)}\s+(?:AS\s+)?(\w+)\b", sql, re.IGNORECASE)
        if m:
            table_alias_in_query[tname] = m.group(1)

    for real_col, owning_table in exclusive.items():
        correct_alias = table_alias_in_query.get(owning_table)
        if not correct_alias:
            continue

        if "_" not in real_col:
            continue

        short_form = real_col.split("_", 1)[1]

        if short_form in exclusive:
            continue

        pattern = rf"\b(\w+)\.{re.escape(short_form)}\b"
        for m in re.finditer(pattern, sql):
            wrong_alias = m.group(1)
            sql = re.sub(
                rf"\b{re.escape(wrong_alias)}\.{re.escape(short_form)}\b",
                f"{correct_alias}.{real_col}",
                sql,
            )

    return sql


def generate_sql(question: str, schema: str, dialect: str = "SQL") -> str:
    llm = get_llm()
    prompt_template = _build_prompt_template(schema)
    chain = prompt_template | llm
    raw_response = chain.invoke({"schema": schema, "question": question, "dialect": dialect})
    sql = clean_sql_output(_extract_text(raw_response))
    sql = extract_sql_statement(sql)
    sql = fix_common_alias_mistakes(sql)
    return fix_hallucinated_column_names(sql)


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
            sql = fix_hallucinated_column_names(
                fix_common_alias_mistakes(extract_sql_statement(clean_sql_output(_extract_text(raw))))
            )

    return sql
