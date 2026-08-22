"""
Database service: one abstraction for SQLite, MySQL, and PostgreSQL.

This is the piece that makes "local vs remote" a config change instead
of a code change. build_database_url() reads DatabaseConfig and returns
a SQLAlchemy URL; get_engine() builds a (cached) engine from it. The
rest of the app (schema service, SQL executor) only ever talks to the
engine — it never knows or cares whether that engine points at a local
SQLite file, a laptop's MySQL, or a managed cloud Postgres instance.
"""
from functools import lru_cache

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from app.config import DatabaseConfig, load_db_config


class DatabaseConnectionError(Exception):
    """Raised when the configured database cannot be reached."""


def build_database_url(cfg: DatabaseConfig) -> str:
    if cfg.db_type == "sqlite":
        # sqlite:///relative/path.db  or  sqlite:////absolute/path.db
        return f"sqlite:///{cfg.sqlite_path}"

    if cfg.db_type == "mysql":
        if not all([cfg.host, cfg.name, cfg.user]):
            raise DatabaseConnectionError(
                "MySQL config incomplete: DB_HOST, DB_NAME, DB_USER are required."
            )
        port = cfg.port or "3306"
        url = (
            f"mysql+pymysql://{cfg.user}:{cfg.password or ''}"
            f"@{cfg.host}:{port}/{cfg.name}"
        )
        if cfg.ssl_mode:
            # pymysql expects ssl params; "require" is the common managed-DB case
            url += "?ssl_verify_cert=true" if cfg.ssl_mode != "disable" else ""
        return url

    if cfg.db_type in ("postgresql", "postgres"):
        if not all([cfg.host, cfg.name, cfg.user]):
            raise DatabaseConnectionError(
                "PostgreSQL config incomplete: DB_HOST, DB_NAME, DB_USER are required."
            )
        port = cfg.port or "5432"
        url = (
            f"postgresql+psycopg2://{cfg.user}:{cfg.password or ''}"
            f"@{cfg.host}:{port}/{cfg.name}"
        )
        if cfg.ssl_mode:
            url += f"?sslmode={cfg.ssl_mode}"
        return url

    raise DatabaseConnectionError(f"Unsupported DB_TYPE: {cfg.db_type!r}")


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    """
    Returns a cached SQLAlchemy engine built from current environment
    config. Cached because engines are meant to be reused/pooled, not
    recreated per request.
    """
    cfg = load_db_config()
    url = build_database_url(cfg)
    try:
        engine = create_engine(url, pool_pre_ping=True)
        # Fail fast with a clear error rather than a confusing traceback
        # deep in SQLAlchemy the first time a query runs.
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return engine
    except SQLAlchemyError as exc:
        raise DatabaseConnectionError(
            f"Could not connect to {cfg.db_type} database at "
            f"{cfg.host or cfg.sqlite_path}: {exc}"
        ) from exc


def reset_engine_cache() -> None:
    """Call after changing env vars at runtime (e.g. in tests) to force a rebuild."""
    get_engine.cache_clear()


def execute_readonly_query(sql: str, max_rows: int) -> tuple[list[str], list[tuple]]:
    """
    Executes a SELECT statement and returns (column_names, rows).
    Assumes the SQL has already passed validation (see app/sql/validator.py).
    """
    engine = get_engine()
    try:
        with engine.connect() as conn:
            result = conn.execute(text(sql))
            columns = list(result.keys())
            rows = result.fetchmany(max_rows)
            return columns, [tuple(r) for r in rows]
    except SQLAlchemyError as exc:
        raise DatabaseConnectionError(f"Query execution failed: {exc}") from exc