"""
Backward-compatible entry point.

The actual logic now lives in app/pipeline.py, app/db/, app/llm/, and
app/sql/ — this file just re-exports get_data_from_database() so any
existing import (`from main import get_data_from_database`) still works.
"""
from app.pipeline import get_data_from_database, QueryResult  # noqa: F401

if __name__ == "__main__":
    import sys

    question = " ".join(sys.argv[1:]) or "Show me the top 5 customers by total order amount"
    result = get_data_from_database(question)
    print(f"Question: {result.question}")
    print(f"SQL: {result.sql}")
    if result.success:
        print(f"Columns: {result.columns}")
        for row in result.rows:
            print(row)
    else:
        print(f"Error: {result.error}")