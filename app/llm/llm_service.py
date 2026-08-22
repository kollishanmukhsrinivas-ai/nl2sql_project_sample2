"""
LLM service: one factory function that returns a configured chat model,
based entirely on LLM_PROVIDER in the environment. Swapping providers
never requires touching the SQL-generation code — only the .env file.

Supported providers:
  - ollama    : fully local, free, no API key (requires `ollama serve` running)
  - groq      : cloud, free tier, fast (requires LLM_API_KEY)
  - openai    : cloud, paid (requires LLM_API_KEY)
  - anthropic : cloud, paid (requires LLM_API_KEY)
"""
from app.config import load_llm_config


class LLMConfigError(Exception):
    """Raised when required config for the selected provider is missing."""


def get_llm():
    cfg = load_llm_config()

    if cfg.provider == "ollama":
        # Local inference via Ollama — no internet, no API key needed.
        from langchain_ollama import OllamaLLM
        return OllamaLLM(
            model=cfg.model or "llama3",
            base_url=cfg.ollama_base_url,
            temperature=cfg.temperature,
        )

    if cfg.provider == "groq":
        if not cfg.api_key:
            raise LLMConfigError("LLM_PROVIDER=groq requires LLM_API_KEY to be set.")
        from langchain_groq import ChatGroq
        return ChatGroq(
            model=cfg.model or "llama3-70b-8192",
            api_key=cfg.api_key,
            temperature=cfg.temperature,
        )

    if cfg.provider == "openai":
        if not cfg.api_key:
            raise LLMConfigError("LLM_PROVIDER=openai requires LLM_API_KEY to be set.")
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=cfg.model or "gpt-4o-mini",
            api_key=cfg.api_key,
            temperature=cfg.temperature,
        )

    if cfg.provider == "anthropic":
        if not cfg.api_key:
            raise LLMConfigError("LLM_PROVIDER=anthropic requires LLM_API_KEY to be set.")
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(
            model=cfg.model or "claude-sonnet-4-5-20250929",
            api_key=cfg.api_key,
            temperature=cfg.temperature,
        )

    raise LLMConfigError(f"Unknown LLM_PROVIDER: {cfg.provider!r}")