# AI Data Analyst 2.0

Turn natural language questions into executable SQL against your local SQLite database. This project uses LangChain with local Ollama models and runs on the ultra-fast `uv` Python package manager.

## Features
- Automatic schema extraction from `amazon.db`
- Natural language to SQL using local LLM (Ollama)
- Deterministic SQL generation (`temperature=0`)
- Easily switch models (e.g. DeepSeek-R1 vs QwenCoder)
- Simple Python API (`get_data_from_database(prompt)`) for integration
- Fast environment setup and dependency management via `uv`

## Tech Stack
- Python 3.11+
- SQLite (`amazon.db`)
- SQLAlchemy for schema introspection
- LangChain Core + Community + Ollama integration
- Ollama local models (recommend: `qwen2.5-coder:7b` for speed)
- `uv` for dependency resolution, syncing, and running

## Architecture
1. Extract schema using SQLAlchemy inspector
2. Feed schema + user question to an LLM prompt template
3. Model returns a SQL query (reasoning models may include `<think>` blocks – we strip or avoid them)
4. Execute SQL safely against `amazon.db`
5. Return results list

```
main.py
└─ extract_schema() -> text_to_sql() -> get_data_from_database()
```

## Prerequisites
- Install Ollama: https://ollama.com/download
- Pull a model (choose one):
  - Fast coder model:
    ```bash
    ollama pull qwen2.5-coder:7b
    ```
  - Reasoning model (slower):
    ```bash
    ollama pull deepseek-r1:8b
    ```
- Ensure `amazon.db` exists in the project root.

## Setup (UV)
No need to manually create a virtual environment—`uv` handles it.

```bash
# Install uv if not present
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install dependencies from pyproject.toml
uv sync

# Run a module or script
uv run python main.py
```

To add a new dependency:
```bash
uv add package_name
```

To upgrade dependencies:
```bash
uv lock --upgrade
uv sync
```

## Usage
Python API example:
```python
from main import get_data_from_database
results = get_data_from_database("Show the first 5 products")
print(results)
```

Direct script run (if you extend `main.py` with CLI later):
```bash
uv run python main.py
```

### Switching Models
Edit `main.py`:
```python
model = OllamaLLM(model="qwen2.5-coder:7b", temperature=0)
```
If you use DeepSeek-R1 models and see long delays, they generate hidden reasoning. Mitigations:
- Add: "Do not use <think> tags." to system prompt
- Strip with regex: `re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL)`
- Prefer a non-reasoning coder model for performance

### Validating Generated SQL (Optional)
Before execution you can add a lightweight validator:
```python
if not sql_query.lower().startswith("select"):
    raise ValueError("Only SELECT queries are allowed.")
```
Add more guards (block DROP/DELETE/UPDATE) for safety.

## Performance Tips
- Use smaller local models (`qwen2.5-coder:7b`) for snappy responses
- Keep `temperature=0` for deterministic output
- Cache schema: avoid recomputing `extract_schema` each call
- (Advanced) Stream model output and stop at first semicolon `;` if the model over-explains

## Troubleshooting
| Issue | Cause | Fix |
|-------|-------|-----|
| Long response time | Reasoning model generating chains | Switch to coder model |
| SQL errors (no such column) | Model hallucinated | Strengthen prompt, show schema clearly |
| Empty results | Query valid but data missing | Inspect `amazon.db` contents |
| Ollama connection error | Service not running | Run `ollama serve` or open app |

## Roadmap / Ideas
- Streamlit frontend (`frontend.py`) to ask questions interactively
- Add SQL validation & sandboxing
- Implement caching layer for repeated queries
- Add tests (unit test for `text_to_sql` stub + schema extraction)
- Support multiple databases (Postgres, DuckDB)

## Security Notes
Executing arbitrary LLM-generated SQL can be risky. Restrict to read-only queries and sanitize user inputs if you later interpolate values.

## Contributing
1. Fork & branch
2. Make changes
3. Run `uv sync && uv run python -m py_compile main.py`
4. Submit PR

## License
MIT (adjust in `pyproject.toml` if you choose a different one)

---
Built with local AI + fast Python tooling.
