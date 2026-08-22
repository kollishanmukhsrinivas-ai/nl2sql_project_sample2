"""
Central configuration for AI Data Analyst 2.0.

Everything here is read from environment variables (optionally loaded
from a local .env file). Nothing is hard-coded — change the .env file
to switch between local/remote databases or local/cloud LLMs without
touching any code.
"""
import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


def _get(name: str, default: str | None = None) -> str | None:
    val = os.environ.get(name, default)
    return val.strip() if isinstance(val, str) else val


def _get_bool(name: str, default: bool = False) -> bool:
    val = os.environ.get(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class DatabaseConfig:
    db_type: str
    host: str | None
    port: str | None
    name: str | None
    user: str | None
    password: str | None
    sqlite_path: str | None
    ssl_mode: str | None


@dataclass(frozen=True)
class LLMConfig:
    provider: str
    api_key: str | None
    model: str | None
    ollama_base_url: str
    temperature: float


def load_db_config() -> DatabaseConfig:
    return DatabaseConfig(
        db_type=_get("DB_TYPE", "sqlite").lower(),
        host=_get("DB_HOST"),
        port=_get("DB_PORT"),
        name=_get("DB_NAME"),
        user=_get("DB_USER"),
        password=_get("DB_PASSWORD"),
        sqlite_path=_get("DB_SQLITE_PATH", "amazon.db"),
        ssl_mode=_get("DB_SSL_MODE"),
    )


def load_llm_config() -> LLMConfig:
    return LLMConfig(
        provider=_get("LLM_PROVIDER", "ollama").lower(),
        api_key=_get("LLM_API_KEY"),
        model=_get("LLM_MODEL"),
        ollama_base_url=_get("OLLAMA_BASE_URL", "http://localhost:11434"),
        temperature=float(_get("LLM_TEMPERATURE", "0") or 0),
    )


ALLOW_WRITE_QUERIES = _get_bool("ALLOW_WRITE_QUERIES", False)
MAX_RESULT_ROWS = int(_get("MAX_RESULT_ROWS", "200") or 200)