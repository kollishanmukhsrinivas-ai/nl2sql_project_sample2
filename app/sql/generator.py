"""
Natural-language question -> SQL, grounded in the live database schema.

Column-location rules and the "combined name" fix are both derived
fresh from whatever schema is actually connected (see schema_service.py
helpers), rather than hardcoded for one specific database — so this
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

{dynamic_column_rules}

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


def fix_common_alias_mistakes(sql: str) -> str:
    """
    Mechanically corrects the model's most persistent mistake: using a
    combined `.name` column on a table that only has separate
    first/last name columns. Which table(s) this applies to is derived
    fresh from the live schema, so it keeps working even if that table
    gets renamed or restructured.
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
    return sql


def generate_sql(question: str, schema: str, dialect: str = "SQL") -> str:
    llm = get_llm()
    prompt_template = _build_prompt_template(schema)
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
