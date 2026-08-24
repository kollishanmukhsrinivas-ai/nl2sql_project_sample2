"""
Schema retrieval service.

Dynamically inspects whatever database get_engine() currently points
at (SQLite, MySQL, or Postgres — local or remote) and produces a
compact, LLM-friendly schema description. Nothing here is tied to any
specific table or column name, so it adapts automatically if you point
the app at a different database.

Includes lightweight, fully offline schema-linking: instead of always
sending every table to the LLM, get_schema_description(question) can
filter down to just the tables relevant to the question (matched by
simple keyword overlap, then expanded one hop via foreign keys so
joins still work), which shrinks the prompt and reduces the chance of
the model reasoning over irrelevant tables/columns. No embeddings, no
network calls — pure string matching, so it works fully offline.
"""
import re

from sqlalchemy import inspect

from app.db.database_service import get_engine


# Common English words that cause false-positive matches against
# column names (e.g. "is" matching "is_primary", "on" matching a
# column with "on" in it). Filtered out of the QUESTION only — table
# vocabularies are left untouched.
_STOPWORDS = {
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "who", "whom", "what", "which", "where", "when", "why", "how",
    "on", "in", "at", "to", "for", "of", "by", "with", "from", "as",
    "and", "or", "not", "no", "do", "does", "did", "has", "have", "had",
    "show", "list", "find", "get", "give", "all", "each", "any", "their",
    "them", "this", "that", "these", "those", "along", "also",
}


def _tokenize(text: str) -> set[str]:
    """Splits on non-alphanumeric characters and lowercases, e.g.
    'base_salary' -> {'base', 'salary'}."""
    return set(re.split(r"[^a-z0-9]+", text.lower())) - {""}


def _build_table_metadata(inspector) -> dict:
    """
    For every table, returns:
      - pk_columns: set of primary key column names
      - fk_map: local_column -> "referred_table.referred_column"
      - fk_neighbors: set of table names this table has an FK relationship with
        (in either direction)
      - vocabulary: set of tokens derived from the table name and its own
        real (non-FK) column names, used for keyword matching against a
        question. FK columns are excluded from vocabulary because they
        just link to another table's rows (e.g. department_id on
        employees) and shouldn't make THIS table match a question about
        that OTHER table's actual topic.
      - columns: raw column list from the inspector
    """
    table_names = inspector.get_table_names()
    metadata = {}

    for table_name in table_names:
        pk_columns = set(inspector.get_pk_constraint(table_name).get("constrained_columns") or [])

        fk_map = {}
        fk_neighbors = set()
        for fk in inspector.get_foreign_keys(table_name):
            for local_col, remote_col in zip(fk["constrained_columns"], fk["referred_columns"]):
                fk_map[local_col] = f"{fk['referred_table']}.{remote_col}"
                fk_neighbors.add(fk["referred_table"])

        columns = inspector.get_columns(table_name)

        vocabulary = set(_tokenize(table_name))
        for col in columns:
            if col["name"] in fk_map:
                continue
            vocabulary |= _tokenize(col["name"])

        metadata[table_name] = {
            "pk_columns": pk_columns,
            "fk_map": fk_map,
            "fk_neighbors": fk_neighbors,
            "vocabulary": vocabulary,
            "columns": columns,
        }

    # Make FK relationships symmetric (if A references B, B should also
    # know it's connected to A) so the 1-hop expansion below works both
    # ways.
    for table_name, meta in metadata.items():
        for neighbor in list(meta["fk_neighbors"]):
            if neighbor in metadata:
                metadata[neighbor]["fk_neighbors"].add(table_name)

    return metadata


def _select_relevant_tables(question: str, metadata: dict) -> set[str]:
    """
    Returns the set of table names relevant to `question`, based on
    keyword overlap with each table's vocabulary, expanded one hop via
    foreign keys so joins between matched tables still work.

    Falls back to ALL tables if nothing matches (safety net — never
    silently hide a table the question actually needed).
    """
    question_tokens = _tokenize(question) - _STOPWORDS
    if not question_tokens:
        return set(metadata.keys())

    directly_matched = set()
    for table_name, meta in metadata.items():
        if question_tokens & meta["vocabulary"]:
            directly_matched.add(table_name)

    if not directly_matched:
        return set(metadata.keys())

    expanded = set(directly_matched)
    for table_name in directly_matched:
        expanded |= metadata[table_name]["fk_neighbors"]

    return expanded


def _format_table(table_name: str, meta: dict) -> list[str]:
    col_descriptions = []
    for col in meta["columns"]:
        desc = f"{col['name']} ({col['type']}"
        if col["name"] in meta["pk_columns"]:
            desc += ", PK"
        if col["name"] in meta["fk_map"]:
            desc += f", FK -> {meta['fk_map'][col['name']]}"
        desc += ")"
        col_descriptions.append(desc)

    return [
        f"Table: {table_name}",
        f"  Columns: {', '.join(col_descriptions)}",
    ]


def get_schema_description(question: str | None = None) -> str:
    """
    Returns a plain-text schema description like:

        Table: customers
          Columns: customer_id (INTEGER, PK), name (TEXT), email (TEXT)
        Table: orders
          Columns: order_id (INTEGER, PK), customer_id (INTEGER, FK -> customers.customer_id), ...

    This is what gets embedded in the LLM prompt so SQL generation is
    grounded in the real, current schema instead of a hard-coded one.

    If `question` is provided, only tables relevant to it (by keyword
    match, expanded one hop via foreign keys) are included — this
    shrinks the prompt and reduces irrelevant-table confusion for
    smaller models. Pass question=None (or omit it) to always get the
    full schema, e.g. for debugging.
    """
    engine = get_engine()
    inspector = inspect(engine)

    metadata = _build_table_metadata(inspector)
    if not metadata:
        return "No tables found in the connected database."

    if question is not None:
        relevant_tables = _select_relevant_tables(question, metadata)
    else:
        relevant_tables = set(metadata.keys())

    lines = []
    for table_name in inspector.get_table_names():
        if table_name not in relevant_tables:
            continue
        lines.extend(_format_table(table_name, metadata[table_name]))

    if not lines:
        return "No tables found in the connected database."

    return "\n".join(lines)


def list_tables() -> list[str]:
    """Convenience helper — used by health-check / debugging endpoints."""
    return inspect(get_engine()).get_table_names()
def get_exclusive_columns() -> dict[str, str]:
    """
    Returns {column_name: table_name} for every column name that
    appears in exactly ONE table across the whole database. These are
    the columns worth telling the model "this lives ONLY here" about —
    computed fresh from whatever schema is actually connected, so it
    stays correct even if columns move, get renamed, or tables change.
    """
    engine = get_engine()
    inspector = inspect(engine)
    metadata = _build_table_metadata(inspector)

    column_to_tables: dict[str, set[str]] = {}
    for table_name, meta in metadata.items():
        for col in meta["columns"]:
            column_to_tables.setdefault(col["name"], set()).add(table_name)

    return {
        col: next(iter(tables))
        for col, tables in column_to_tables.items()
        if len(tables) == 1
    }


def get_composite_name_tables() -> dict[str, tuple[str, str]]:
    """
    Returns {table_name: (first_name_col, last_name_col)} for every
    table that has separate first/last name columns but NO single
    combined 'name' column — the exact shape that causes models to
    hallucinate a nonexistent `.name` column. Computed fresh from the
    live schema, so it adapts automatically if this table gets renamed
    or a differently-shaped employee table replaces it.
    """
    engine = get_engine()
    inspector = inspect(engine)
    metadata = _build_table_metadata(inspector)

    result = {}
    for table_name, meta in metadata.items():
        col_names = {c["name"] for c in meta["columns"]}
        has_name = any(c in col_names for c in ("name", "full_name", "employee_name"))
        first_candidates = [c for c in col_names if "first" in c and "name" in c]
        last_candidates = [c for c in col_names if "last" in c and "name" in c]
        if first_candidates and last_candidates and not has_name:
            result[table_name] = (first_candidates[0], last_candidates[0])

    return result
