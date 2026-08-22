"""
SQL validation / safety layer.

The LLM's output is NEVER executed directly. Every generated query
passes through here first. By default only single, read-only SELECT
(or WITH ... SELECT CTE) statements are allowed — matching the
"prefer read-only NL2SQL initially" requirement. Set
ALLOW_WRITE_QUERIES=true in .env to lift this (not recommended without
adding per-table authorization on top).
"""
import re

from app.config import ALLOW_WRITE_QUERIES

_FORBIDDEN_KEYWORDS = [
    "DROP", "DELETE", "UPDATE", "ALTER", "TRUNCATE",
    "INSERT", "CREATE", "GRANT", "REVOKE", "REPLACE",
    "ATTACH", "DETACH", "PRAGMA", "VACUUM",
]


class SQLValidationError(Exception):
    """Raised when generated SQL fails the safety check."""


def _strip_trailing_semicolon(sql: str) -> str:
    sql = sql.strip()
    if sql.endswith(";"):
        sql = sql[:-1].strip()
    return sql


def validate_sql(sql: str) -> str:
    """
    Validates `sql` and returns the cleaned, single-statement SQL if safe.
    Raises SQLValidationError with a human-readable reason otherwise.
    """
    if not sql or not sql.strip():
        raise SQLValidationError("The model returned an empty SQL query.")

    sql = _strip_trailing_semicolon(sql)

    # Block statement chaining (e.g. "SELECT ...; DROP TABLE ...").
    if ";" in sql:
        raise SQLValidationError(
            "Multiple SQL statements are not allowed in a single query."
        )

    normalized = sql.strip().upper()

    if not ALLOW_WRITE_QUERIES:
        if not (normalized.startswith("SELECT") or normalized.startswith("WITH")):
            raise SQLValidationError(
                "Only read-only SELECT queries are allowed "
                "(set ALLOW_WRITE_QUERIES=true to change this)."
            )

    # Word-boundary match so this doesn't false-positive on e.g. a column
    # named "updated_at" while still catching UPDATE/DELETE/etc. as keywords.
    for keyword in _FORBIDDEN_KEYWORDS:
        if re.search(rf"\b{keyword}\b", normalized):
            raise SQLValidationError(
                f"Generated SQL contains a disallowed operation: {keyword}."
            )

    return sql