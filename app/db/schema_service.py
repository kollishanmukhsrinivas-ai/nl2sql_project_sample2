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
simple keyword overlap, then expanded via foreign keys up to `hops`
steps so multi-table joins still work), which shrinks the prompt and
reduces the chance of the model reasoning over irrelevant
tables/columns. No embeddings, no network calls — pure string
matching, so it works fully offline.
"""
import re

from sqlalchemy import inspect, text

from app.db.database_service import get_engine


_STOPWORDS = {
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "who", "whom", "what", "which", "where", "when", "why", "how",
    "on", "in", "at", "to", "for", "of", "by", "with", "from", "as",
    "and", "or", "not", "no", "do", "does", "did", "has", "have", "had",
    "show", "list", "find", "get", "give", "all", "each", "any", "their",
    "them", "this", "that", "these", "those", "along", "also",
}


def _tokenize(text_value: str) -> set[str]:
    return set(re.split(r"[^a-z0-9]+", text_value.lower())) - {""}


def _build_table_metadata(inspector) -> dict:
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

    for table_name, meta in metadata.items():
        for neighbor in list(meta["fk_neighbors"]):
            if neighbor in metadata:
                metadata[neighbor]["fk_neighbors"].add(table_name)

    return metadata


def _select_relevant_tables(question: str, metadata: dict, hops: int = 2) -> set[str]:
    """
    Keyword-match tables against the question, then expand outward
    along FK edges up to `hops` steps (BFS), so join paths that need
    an intermediate "bridge" table (e.g. leaves -> employees ->
    departments) are still fully included instead of being cut off
    after a single hop.
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
    frontier = set(directly_matched)

    for _ in range(hops):
        next_frontier = set()
        for table_name in frontier:
            next_frontier |= metadata[table_name]["fk_neighbors"]
        next_frontier -= expanded
        if not next_frontier:
            break
        expanded |= next_frontier
        frontier = next_frontier

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


def get_schema_description(question: str | None = None, hops: int = 2) -> str:
    engine = get_engine()
    inspector = inspect(engine)

    metadata = _build_table_metadata(inspector)
    if not metadata:
        return "No tables found in the connected database."

    if question is not None:
        relevant_tables = _select_relevant_tables(question, metadata, hops=hops)
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
    return inspect(get_engine()).get_table_names()


def get_exclusive_columns() -> dict[str, str]:
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


def get_sample_values(max_distinct: int = 8) -> dict[str, list[str]]:
    """
    Returns {"table.column": [sample values]} for VARCHAR/TEXT columns
    with low cardinality (<= max_distinct distinct values). Narrative
    free-text columns are excluded even if they happen to have few
    distinct values in a small dataset, since they're searched with
    LIKE, not matched exactly.
    """
    engine = get_engine()
    inspector = inspect(engine)
    result = {}
    free_text_markers = (
        "description", "comment", "remark", "note",
        "goal", "strength", "weakness", "certificate",
        "address", "reason",
    )
    with engine.connect() as conn:
        for table_name in inspector.get_table_names():
            for col in inspector.get_columns(table_name):
                col_type = str(col["type"]).upper()
                if "CHAR" not in col_type and "TEXT" not in col_type:
                    continue
                name = col["name"].lower()
                if any(marker in name for marker in free_text_markers):
                    continue
                rows = conn.execute(
                    text(
                        f"SELECT DISTINCT `{col['name']}` FROM `{table_name}` "
                        f"WHERE `{col['name']}` IS NOT NULL LIMIT {max_distinct + 1}"
                    )
                ).fetchall()
                values = [r[0] for r in rows]
                if 1 <= len(values) <= max_distinct:
                    result[f"{table_name}.{col['name']}"] = values
    return result


def get_composite_name_tables() -> dict[str, tuple[str, str]]:
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
