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
        #
        # num_ctx controls the context window (and therefore the KV cache
        # size Ollama has to keep in VRAM). NL2SQL prompts are short —
        # schema + question + generated SQL rarely approaches even 2048
        # tokens — so there's no reason to pay for Ollama's 4096 default.
        # On VRAM-constrained GPUs, a smaller num_ctx can be the difference
        # between the model fully fitting on GPU vs. partially falling
        # back to CPU (which is dramatically slower).
        print(f"[DEBUG] Ollama config -> model={cfg.model!r}, num_ctx={cfg.ollama_num_ctx!r}")

        from langchain_ollama import OllamaLLM
        return OllamaLLM(
            model=cfg.model or "llama3",
            base_url=cfg.ollama_base_url,
            temperature=cfg.temperature,
            num_ctx=cfg.ollama_num_ctx,
            keep_alive=cfg.ollama_keep_alive, 
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
