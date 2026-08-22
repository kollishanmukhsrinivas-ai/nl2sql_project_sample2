import time

import pandas as pd
import streamlit as st

from app.config import load_db_config, load_llm_config
from app.pipeline import get_data_from_database

st.set_page_config(page_title="AI Data Analyst", page_icon="🧠", layout="wide")

st.markdown(
    """
    <style>
    .big-title { font-size: 2.1rem; font-weight: 700; margin-bottom: 0; }
    .subtitle { color: #9aa0a6; margin-top: 0; margin-bottom: 1rem; }
    div[data-testid="stChatMessage"] { padding: 0.6rem 1rem; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------- Sidebar ----------
with st.sidebar:
    st.header("⚙️ Connection")
    try:
        db_cfg = load_db_config()
        st.success(f"Database: **{db_cfg.db_type}**")
        st.caption(
            f"File: `{db_cfg.sqlite_path}`" if db_cfg.db_type == "sqlite"
            else f"Host: `{db_cfg.host}:{db_cfg.port}` • DB: `{db_cfg.name}`"
        )
    except Exception as exc:
        st.error(f"Database config error: {exc}")

    try:
        llm_cfg = load_llm_config()
        st.success(f"LLM: **{llm_cfg.provider}** ({llm_cfg.model or 'default'})")
    except Exception as exc:
        st.error(f"LLM config error: {exc}")

    st.divider()
    st.caption("💡 Try:")
    examples = [
        "Top 5 customers by total order amount",
        "How many orders per city?",
        "Average product price by category",
        "Orders with more than 1 item",
    ]
    for ex in examples:
        if st.button(ex, use_container_width=True, key=f"ex_{ex}"):
            st.session_state.pending_question = ex

    st.divider()
    if st.button("🗑️ Clear chat", use_container_width=True):
        st.session_state.history = []
        st.rerun()

# ---------- Header ----------
st.markdown('<p class="big-title">🧠 AI Data Analyst</p>', unsafe_allow_html=True)
st.markdown('<p class="subtitle">Ask your database a question — press Enter to run it.</p>', unsafe_allow_html=True)

# ---------- Chat history state ----------
if "history" not in st.session_state:
    st.session_state.history = []  # list of {"question": ..., "result": QueryResult}


def render_result(result, elapsed=None):
    if not result.success:
        st.error(f"❌ {result.error}")
        if result.sql:
            with st.expander("Generated SQL (rejected / failed)"):
                st.code(result.sql, language="sql")
        return

    if elapsed is not None:
        st.caption(f"✅ done in {elapsed:.1f}s")

    tab_result, tab_sql = st.tabs(["📊 Result", "🧾 SQL"])
    with tab_sql:
        st.code(result.sql, language="sql")
    with tab_result:
        if result.rows:
            df = pd.DataFrame(result.rows, columns=result.columns)
            st.dataframe(df, use_container_width=True, hide_index=True)
            st.caption(f"{len(df)} row(s) returned.")
            if df.shape[1] == 2 and pd.api.types.is_numeric_dtype(df.iloc[:, 1]):
                st.bar_chart(df.set_index(df.columns[0]))
        else:
            st.info("Query ran successfully but returned no rows.")


# ---------- Replay chat history ----------
for turn in st.session_state.history:
    with st.chat_message("user"):
        st.write(turn["question"])
    with st.chat_message("assistant"):
        render_result(turn["result"])

# ---------- Handle a click on an example (acts like a submitted message) ----------
pending = st.session_state.pop("pending_question", None)

# ---------- Chat input — submits on Enter automatically ----------
typed = st.chat_input("Ask a question about your data...")

question = pending or typed

if question:
    with st.chat_message("user"):
        st.write(question)

    with st.chat_message("assistant"):
        start = time.time()
        with st.spinner("Reading schema and generating SQL..."):
            result = get_data_from_database(question)
        elapsed = time.time() - start
        render_result(result, elapsed=elapsed)

    st.session_state.history.append({"question": question, "result": result})