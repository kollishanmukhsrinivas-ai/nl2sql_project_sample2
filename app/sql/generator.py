"""
Natural-language question -> SQL, grounded in the live database schema.
"""
import re

from langchain_core.prompts import ChatPromptTemplate

from app.llm.llm_service import get_llm

SYSTEM_PROMPT = """You are an expert SQL generator for a {dialect} database.
Given a database schema and a user question, generate a single valid,
read-only SELECT SQL query that answers the question.

Rules:
- Only use the tables and columns provided in the schema below. Never invent columns or tables.
- Use explicit JOINs (with ON conditions) when the question requires data from multiple tables.
- Output ONLY the raw SQL query. No explanation, no markdown code fences, no <think> tags, no preamble.
- The query must be a single statement (no semicolons, no multiple statements).
- Never generate INSERT, UPDATE, DELETE, DROP, ALTER, or TRUNCATE statements.

Schema:
{schema}
"""

_prompt_template = ChatPromptTemplate.from_messages([
    ("system", SYSTEM_PROMPT),
    ("user", "Question: {question}\n\nSQL Query:"),
])


def _extract_text(response) -> str:
    """Handles both plain string LLM responses (Ollama) and message objects (chat models)."""
    return response.content if hasattr(response, "content") else str(response)


def clean_sql_output(raw: str) -> str:
    text = raw.strip()
    # Strip <think>...</think> blocks some reasoning models emit
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    # Strip markdown code fences if the model adds them despite instructions
    text = re.sub(r"```sql|```", "", text)
    return text.strip()


def generate_sql(question: str, schema: str, dialect: str = "SQL") -> str:
    llm = get_llm()
    chain = _prompt_template | llm
    raw_response = chain.invoke({"schema": schema, "question": question, "dialect": dialect})
    return clean_sql_output(_extract_text(raw_response))