"""
Orchestrates the full pipeline:

  Question -> Schema Retrieval -> LLM -> Generated SQL -> Validation
  -> Execution -> Result

Every failure mode gets caught and returned as a structured, frontend-
safe dict instead of raising a raw exception with a stack trace or
leaking credentials.
"""
from dataclasses import dataclass, field

from app.config import load_db_config, MAX_RESULT_ROWS
from app.db.database_service import DatabaseConnectionError, execute_readonly_query
from app.db.schema_service import get_schema_description
from app.llm.llm_service import LLMConfigError
from app.sql.generator import generate_sql
from app.sql.validator import SQLValidationError, validate_sql


@dataclass
class QueryResult:
    success: bool
    question: str
    sql: str | None = None
    columns: list[str] = field(default_factory=list)
    rows: list[tuple] = field(default_factory=list)
    error: str | None = None


def get_data_from_database(question: str) -> QueryResult:
    """
    Main entry point used by the frontend. Never raises — always
    returns a QueryResult, with .error set on any failure.
    """
    if not question or not question.strip():
        return QueryResult(success=False, question=question, error="Please enter a question.")

    # 1. Schema retrieval (dynamic — whatever DB is currently configured)
    try:
        schema = get_schema_description()
    except DatabaseConnectionError as exc:
        return QueryResult(success=False, question=question, error=f"Database connection failed: {exc}")

    dialect = load_db_config().db_type

    # 2. LLM: natural language -> SQL
    try:
        sql = generate_sql(question, schema, dialect=dialect)
    except LLMConfigError as exc:
        return QueryResult(success=False, question=question, error=f"LLM configuration error: {exc}")
    except Exception as exc:  # LLM/network failures of any kind
        return QueryResult(success=False, question=question, error=f"The LLM failed to respond: {exc}")

    # 3. Validate the generated SQL before it ever touches the database
    try:
        safe_sql = validate_sql(sql)
    except SQLValidationError as exc:
        return QueryResult(success=False, question=question, sql=sql, error=f"Rejected unsafe SQL: {exc}")

    # 4. Execute against whichever database is currently connected
    try:
        columns, rows = execute_readonly_query(safe_sql, max_rows=MAX_RESULT_ROWS)
    except DatabaseConnectionError as exc:
        return QueryResult(success=False, question=question, sql=safe_sql, error=str(exc))

    return QueryResult(success=True, question=question, sql=safe_sql, columns=columns, rows=rows)