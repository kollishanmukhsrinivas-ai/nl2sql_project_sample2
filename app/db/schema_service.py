"""
Schema retrieval service.

Dynamically inspects whatever database get_engine() currently points
at (SQLite, MySQL, or Postgres — local or remote) and produces a
compact, LLM-friendly schema description. Nothing here is tied to any
specific table or column name, so it adapts automatically if you point
the app at a different database.
"""
from sqlalchemy import inspect

from app.db.database_service import get_engine


def get_schema_description() -> str:
    """
    Returns a plain-text schema description like:

        Table: customers
          Columns: customer_id (INTEGER, PK), name (TEXT), email (TEXT)
        Table: orders
          Columns: order_id (INTEGER, PK), customer_id (INTEGER, FK -> customers.customer_id), ...

    This is what gets embedded in the LLM prompt so SQL generation is
    grounded in the real, current schema instead of a hard-coded one.
    """
    engine = get_engine()
    inspector = inspect(engine)

    lines = []
    for table_name in inspector.get_table_names():
        pk_columns = set(inspector.get_pk_constraint(table_name).get("constrained_columns") or [])

        fk_map = {}
        for fk in inspector.get_foreign_keys(table_name):
            for local_col, remote_col in zip(fk["constrained_columns"], fk["referred_columns"]):
                fk_map[local_col] = f"{fk['referred_table']}.{remote_col}"

        col_descriptions = []
        for col in inspector.get_columns(table_name):
            desc = f"{col['name']} ({col['type']}"
            if col["name"] in pk_columns:
                desc += ", PK"
            if col["name"] in fk_map:
                desc += f", FK -> {fk_map[col['name']]}"
            desc += ")"
            col_descriptions.append(desc)

        lines.append(f"Table: {table_name}")
        lines.append(f"  Columns: {', '.join(col_descriptions)}")

    if not lines:
        return "No tables found in the connected database."

    return "\n".join(lines)


def list_tables() -> list[str]:
    """Convenience helper — used by health-check / debugging endpoints."""
    return inspect(get_engine()).get_table_names()