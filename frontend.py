import time

import pandas as pd
import streamlit as st

from app.config import load_db_config, load_llm_config
from app.pipeline import get_data_from_database


# ============================================================
# PAGE CONFIG
# ============================================================

st.set_page_config(
    page_title="AI Data Analyst",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ============================================================
# CLEAN UI
# ============================================================

st.markdown(
    """
    <style>
        .main .block-container {
            max-width: 1100px;
            padding-top: 2rem;
            padding-bottom: 2rem;
        }

        .app-title {
            font-size: 2rem;
            font-weight: 700;
            margin-bottom: 0;
            color: #111827;
        }

        .app-subtitle {
            color: #6b7280;
            margin-top: 4px;
            margin-bottom: 1.5rem;
        }

        /* Chat spacing */
        div[data-testid="stChatMessage"] {
            padding-top: 0.4rem;
            padding-bottom: 0.4rem;
        }

        /* Smaller dataframe */
        div[data-testid="stDataFrame"] {
            border-radius: 8px;
        }

        /* Sidebar */
        section[data-testid="stSidebar"] {
            background: #f8fafc;
        }

        /* Smaller buttons */
        .stButton > button {
            border-radius: 8px;
        }

        /* -------- Quick chart: bar mode -------- */
        .quick-chart {
            width: 100%;
            max-width: 760px;
            margin-top: 10px;
        }

        .chart-note {
            font-size: 12px;
            color: #9ca3af;
            margin-bottom: 8px;
        }

        .chart-row {
            display: flex;
            align-items: center;
            gap: 12px;
            margin: 7px 0;
        }

        .chart-label {
            width: 150px;
            min-width: 150px;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
            font-size: 13px;
            color: #374151;
            text-align: right;
        }

        .chart-track {
            flex: 1;
            height: 22px;
            background: #f1f5f9;
            border-radius: 6px;
            overflow: hidden;
            position: relative;
        }

        .chart-bar {
            height: 100%;
            border-radius: 6px;
            background: linear-gradient(90deg, #3b82f6, #2563eb);
            transition: width 0.4s ease;
        }

        .chart-bar.negative {
            background: linear-gradient(90deg, #f87171, #dc2626);
        }

        .chart-row:hover .chart-track {
            background: #e5edfb;
        }

        .chart-value {
            width: 78px;
            min-width: 78px;
            font-size: 13px;
            color: #374151;
            font-weight: 600;
            font-variant-numeric: tabular-nums;
        }

        .chart-value.negative { color: #dc2626; }

        /* -------- Quick chart: single-value stat card -------- */
        .stat-card {
            position: relative;
            overflow: hidden;
            max-width: 340px;
            padding: 22px 24px 20px;
            border: 1px solid #e5e7eb;
            border-radius: 16px;
            background: linear-gradient(160deg, #ffffff, #f8fafc);
            box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04), 0 10px 24px -14px rgba(37, 99, 235, 0.35);
        }

        .stat-card-glow {
            position: absolute;
            top: -46px;
            right: -46px;
            width: 150px;
            height: 150px;
            border-radius: 50%;
            background: radial-gradient(circle, rgba(37, 99, 235, 0.14), transparent 70%);
            pointer-events: none;
        }

        .stat-card-top {
            position: relative;
            z-index: 1;
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 10px;
            margin-bottom: 18px;
        }

        .stat-icon {
            width: 38px;
            height: 38px;
            flex-shrink: 0;
            border-radius: 10px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 17px;
            background: linear-gradient(135deg, #3b82f6, #2563eb);
            box-shadow: 0 4px 10px -2px rgba(37, 99, 235, 0.45);
        }

        .stat-chip {
            font-size: 11px;
            font-weight: 600;
            color: #2563eb;
            background: #eff6ff;
            border: 1px solid #dbeafe;
            padding: 4px 11px;
            border-radius: 999px;
            max-width: 190px;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }

        .stat-number {
            position: relative;
            z-index: 1;
            font-size: 34px;
            font-weight: 800;
            color: #111827;
            letter-spacing: -0.02em;
            font-variant-numeric: tabular-nums;
            line-height: 1.1;
        }

        .stat-metric-label {
            position: relative;
            z-index: 1;
            margin-top: 5px;
            font-size: 11.5px;
            font-weight: 600;
            color: #6b7280;
            text-transform: uppercase;
            letter-spacing: 0.06em;
        }

        /* -------- Quick chart: trend mode (time-series) -------- */
        .trend-chart {
            width: 100%;
            max-width: 760px;
            margin-top: 10px;
            border: 1px solid #e5e7eb;
            border-radius: 10px;
            padding: 14px 16px 10px;
            background: #ffffff;
        }

        .trend-header {
            display: flex;
            justify-content: space-between;
            align-items: baseline;
            margin-bottom: 6px;
        }

        .trend-latest-label {
            font-size: 12px;
            color: #6b7280;
        }

        .trend-latest-value {
            font-size: 20px;
            font-weight: 700;
            color: #111827;
            font-variant-numeric: tabular-nums;
        }

        .trend-delta {
            font-size: 12px;
            font-weight: 600;
            margin-left: 8px;
        }

        .trend-delta.up { color: #16a34a; }
        .trend-delta.down { color: #dc2626; }
        .trend-delta.flat { color: #6b7280; }

        .trend-axis-label {
            font-size: 11px;
            color: #9ca3af;
        }
    </style>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# SESSION STATE
# ============================================================

if "history" not in st.session_state:
    st.session_state.history = []

if "pending_question" not in st.session_state:
    st.session_state.pending_question = None


# ============================================================
# CHART HELPERS
# ============================================================

def _flatten_html(html: str) -> str:
    """Collapse a multi-line, indented HTML/SVG string into a single line.

    Streamlit still runs st.markdown() content through a CommonMark
    parser even with unsafe_allow_html=True, and CommonMark treats any
    line indented 4+ spaces as a literal "indented code block" instead
    of HTML. Python f-strings built across multiple indented lines (as
    used below for chart rows / stat cards / SVGs) trigger that rule as
    soon as they're concatenated together, so every row after the first
    renders as raw escaped text instead of a chart.

    Stripping each line and rejoining with a single space removes all
    leading whitespace and newlines, which makes that CommonMark rule
    structurally impossible to trigger — regardless of markdown flavor
    or renderer. A single space (not empty string) is used as the
    separator so that adjacent HTML/SVG attributes that happen to sit
    on separate source lines don't get glued together
    (e.g. y2="160"stroke="#e5e7eb" would be invalid).
    """
    lines = [line.strip() for line in html.strip().splitlines()]
    return " ".join(line for line in lines if line)


def _format_number(value) -> str:
    """Format a numeric value with thousands separators, trimming
    unnecessary decimal noise on whole numbers."""
    if isinstance(value, float):
        if value.is_integer():
            return f"{value:,.0f}"
        return f"{value:,.2f}"
    return f"{value:,}"


def _prettify_column_name(name: str) -> str:
    """turn 'total_quantity' into 'Total Quantity' for display."""
    return name.replace("_", " ").replace("-", " ").strip().title()


def _pick_metric_icon(column_name: str) -> str:
    """Pick a small icon that hints at what kind of metric this is,
    based on common naming conventions in query results."""
    name = column_name.lower()
    if any(k in name for k in ("price", "amount", "revenue", "cost", "sales", "spend", "total_value")):
        return "💰"
    if any(k in name for k in ("quantity", "qty", "count", "orders", "units", "items")):
        return "📦"
    if any(k in name for k in ("rate", "percent", "ratio", "share")):
        return "📈"
    if any(k in name for k in ("customer", "user", "client", "buyer")):
        return "👤"
    if any(k in name for k in ("time", "duration", "seconds", "minutes", "hours", "days")):
        return "⏱️"
    return "✨"


def _pick_label_and_value_columns(df: pd.DataFrame, numeric_columns: list[str]):
    """Choose the most sensible label (dimension) and value (metric) columns.

    The label is the first non-numeric column when one exists, rather than
    blindly the first column — a leading numeric ID column shouldn't win
    over a descriptive text column sitting right next to it.

    The value is whichever numeric column has the widest range, on the
    assumption that a column that barely varies (like a constant flag)
    is less likely to be the metric someone wants visualized.
    """
    non_numeric_columns = [c for c in df.columns if c not in numeric_columns]
    label_column = non_numeric_columns[0] if non_numeric_columns else df.columns[0]

    candidates = [c for c in numeric_columns if c != label_column] or numeric_columns
    value_column = max(
        candidates,
        key=lambda c: (df[c].max() - df[c].min()) if df[c].notna().any() else 0,
    )
    return label_column, value_column


def _looks_like_time_series(series: pd.Series) -> bool:
    """Heuristic: does this column look like dates/periods with enough
    distinct points to plot as a trend rather than discrete bars?"""
    if series.empty or series.nunique() < 4:
        return False
    parsed = pd.to_datetime(series, errors="coerce")
    return parsed.notna().mean() > 0.8


def render_bar_chart(df: pd.DataFrame, label_column: str, value_column: str, total_rows: int):
    """Horizontal bar chart: sorted by magnitude, sign-aware, duplicate
    labels aggregated, capped at 10 with a note when truncated."""

    chart_df = df[[label_column, value_column]].copy()
    chart_df[value_column] = pd.to_numeric(chart_df[value_column], errors="coerce")
    chart_df = chart_df.dropna(subset=[value_column])

    if chart_df.empty:
        return

    # Aggregate if the label repeats, so each label gets exactly one bar.
    if chart_df[label_column].duplicated().any():
        chart_df = chart_df.groupby(label_column, as_index=False)[value_column].sum()

    # Rank by magnitude — "top 10" should mean the 10 largest, not the
    # first 10 rows the query happened to return.
    chart_df = chart_df.reindex(chart_df[value_column].abs().sort_values(ascending=False).index)
    shown = min(10, len(chart_df))
    chart_df = chart_df.head(10)

    if len(chart_df) == 1:
        label = str(chart_df.iloc[0][label_column])
        if len(label) > 26:
            label = label[:26] + "…"
        value = chart_df.iloc[0][value_column]
        icon = _pick_metric_icon(value_column)
        metric_label = _prettify_column_name(value_column)
        st.markdown(
            _flatten_html(
                f"""
                <div class="stat-card">
                    <div class="stat-card-glow"></div>
                    <div class="stat-card-top">
                        <div class="stat-icon">{icon}</div>
                        <div class="stat-chip" title="{label}">{label}</div>
                    </div>
                    <div class="stat-number">{_format_number(value)}</div>
                    <div class="stat-metric-label">{metric_label}</div>
                </div>
                """
            ),
            unsafe_allow_html=True,
        )
        return

    max_abs = chart_df[value_column].abs().max() or 1

    rows_html = []
    for _, row in chart_df.iterrows():
        label = str(row[label_column])
        if len(label) > 22:
            label = label[:22] + "…"

        value = row[value_column]
        is_negative = value < 0
        percentage = max((abs(float(value)) / float(max_abs)) * 100, 2)
        bar_class = "chart-bar negative" if is_negative else "chart-bar"
        value_class = "chart-value negative" if is_negative else "chart-value"

        rows_html.append(
            f"""
            <div class="chart-row">
                <div class="chart-label" title="{label}">{label}</div>
                <div class="chart-track">
                    <div class="{bar_class}" style="width: {percentage:.1f}%;"></div>
                </div>
                <div class="{value_class}">{_format_number(value)}</div>
            </div>
            """
        )

    note = ""
    if total_rows > shown:
        note = f'<div class="chart-note">Showing top {shown} of {total_rows} rows, ranked by {value_column}.</div>'

    final_html = f'<div class="quick-chart">{note}{"".join(rows_html)}</div>'
    st.markdown(_flatten_html(final_html), unsafe_allow_html=True)


def render_trend_chart(df: pd.DataFrame, label_column: str, value_column: str):
    """Lightweight inline SVG trend line for time-series results — a
    filled area chart with a smoothed line, endpoint highlight, and a
    delta vs. the previous point, since a row of bars is the wrong shape
    for 'how did this change over time'."""

    chart_df = df[[label_column, value_column]].copy()
    chart_df[value_column] = pd.to_numeric(chart_df[value_column], errors="coerce")
    chart_df["_parsed_date"] = pd.to_datetime(chart_df[label_column], errors="coerce")
    chart_df = chart_df.dropna(subset=[value_column, "_parsed_date"]).sort_values("_parsed_date")

    if len(chart_df) < 2:
        return render_bar_chart(df, label_column, value_column, len(df))

    values = chart_df[value_column].tolist()
    labels = chart_df[label_column].astype(str).tolist()

    width, height, pad_x, pad_y = 700, 160, 10, 18
    v_min, v_max = min(values), max(values)
    v_range = (v_max - v_min) or 1

    def scale_x(i):
        if len(values) == 1:
            return pad_x
        return pad_x + (i / (len(values) - 1)) * (width - 2 * pad_x)

    def scale_y(v):
        return height - pad_y - ((v - v_min) / v_range) * (height - 2 * pad_y)

    points = [(scale_x(i), scale_y(v)) for i, v in enumerate(values)]

    line_path = f"M {points[0][0]:.1f} {points[0][1]:.1f} " + " ".join(
        f"L {x:.1f} {y:.1f}" for x, y in points[1:]
    )
    area_path = (
        line_path
        + f" L {points[-1][0]:.1f} {height - pad_y} L {points[0][0]:.1f} {height - pad_y} Z"
    )

    last_x, last_y = points[-1]

    latest_value = values[-1]
    delta = latest_value - values[-2]
    if abs(delta) < 1e-9:
        delta_class, delta_arrow = "flat", "→"
    elif delta > 0:
        delta_class, delta_arrow = "up", "↑"
    else:
        delta_class, delta_arrow = "down", "↓"

    svg = f"""
    <svg viewBox="0 0 {width} {height}" width="100%" height="{height}" preserveAspectRatio="none">
        <defs>
            <linearGradient id="trendFill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stop-color="#2563eb" stop-opacity="0.18" />
                <stop offset="100%" stop-color="#2563eb" stop-opacity="0" />
            </linearGradient>
        </defs>
        <line x1="{pad_x}" y1="{height - pad_y}" x2="{width - pad_x}" y2="{height - pad_y}"
              stroke="#e5e7eb" stroke-width="1" />
        <path d="{area_path}" fill="url(#trendFill)" stroke="none" />
        <path d="{line_path}" fill="none" stroke="#2563eb" stroke-width="2.5"
              stroke-linejoin="round" stroke-linecap="round" />
        <circle cx="{last_x:.1f}" cy="{last_y:.1f}" r="4" fill="#2563eb" stroke="#ffffff" stroke-width="2" />
    </svg>
    """

    final_html = f"""
    <div class="trend-chart">
        <div class="trend-header">
            <div>
                <span class="trend-latest-value">{_format_number(latest_value)}</span>
                <span class="trend-delta {delta_class}">{delta_arrow} {_format_number(abs(delta))}</span>
            </div>
            <div class="trend-latest-label">{value_column} · latest: {labels[-1]}</div>
        </div>
        {svg}
        <div style="display:flex; justify-content:space-between;">
            <span class="trend-axis-label">{labels[0]}</span>
            <span class="trend-axis-label">{labels[-1]}</span>
        </div>
    </div>
    """

    st.markdown(_flatten_html(final_html), unsafe_allow_html=True)


def render_quick_chart(df: pd.DataFrame):
    """Pick the right visualization for the shape of the data: a trend
    line for time-series results, otherwise a ranked horizontal bar
    chart — no Plotly, no Streamlit chart grid, just clean inline SVG/HTML."""

    if df.empty or len(df.columns) < 2:
        return

    numeric_columns = df.select_dtypes(include="number").columns.tolist()
    if not numeric_columns:
        return

    label_column, value_column = _pick_label_and_value_columns(df, numeric_columns)

    if _looks_like_time_series(df[label_column]):
        render_trend_chart(df, label_column, value_column)
    else:
        render_bar_chart(df, label_column, value_column, total_rows=len(df))


# ============================================================
# RESULT DISPLAY
# ============================================================

def display_results(result, elapsed=None):
    """Display SQL, result table, metrics and small visualization."""

    if not result.success:

        st.error(f"⚠️ {result.error}")

        if result.sql:
            with st.expander("Generated SQL"):
                st.code(
                    result.sql,
                    language="sql",
                )

        return

    # --------------------------------------------------------
    # Execution information
    # --------------------------------------------------------

    if elapsed is not None:
        st.caption(
            f"✓ Completed in {elapsed:.2f}s"
        )

    # --------------------------------------------------------
    # Tabs
    # --------------------------------------------------------

    tab_result, tab_sql = st.tabs(
        [
            "📊 Result",
            "🧾 SQL",
        ]
    )

    # --------------------------------------------------------
    # SQL
    # --------------------------------------------------------

    with tab_sql:

        if result.sql:
            st.code(
                result.sql,
                language="sql",
            )

    # --------------------------------------------------------
    # RESULT
    # --------------------------------------------------------

    with tab_result:

        if not result.rows:

            st.info(
                "The query ran successfully but returned no rows."
            )

            return

        df = pd.DataFrame(
            result.rows,
            columns=result.columns,
        )

        # ----------------------------------------------------
        # Metrics
        # ----------------------------------------------------

        col1, col2 = st.columns(2)

        with col1:
            st.metric(
                "Rows",
                f"{len(df):,}",
            )

        with col2:
            st.metric(
                "Columns",
                f"{len(df.columns):,}",
            )

        st.markdown("")

        # ----------------------------------------------------
        # Data table
        # ----------------------------------------------------

        st.dataframe(
            df,
            use_container_width=True,
            hide_index=True,
            height=min(
                400,
                max(120, 45 + len(df) * 35),
            ),
        )

        # ----------------------------------------------------
        # Download
        # ----------------------------------------------------

        csv_data = df.to_csv(
            index=False
        ).encode("utf-8")

        st.download_button(
            label="⬇️ Download CSV",
            data=csv_data,
            file_name="query_results.csv",
            mime="text/csv",
        )

        # ----------------------------------------------------
        # Visualization
        # ----------------------------------------------------

        if len(df.columns) >= 2:

            numeric_columns = df.select_dtypes(
                include="number"
            ).columns.tolist()

            if numeric_columns:

                st.markdown("")
                st.markdown("**📊 Quick Visualization**")

                render_quick_chart(df)


# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:

    st.header("⚙️ Connection")

    # --------------------------------------------------------
    # Database
    # --------------------------------------------------------

    try:

        db_cfg = load_db_config()

        st.success(
            f"Database: **{db_cfg.db_type}**"
        )

        if db_cfg.db_type == "sqlite":

            st.caption(
                f"File: `{db_cfg.sqlite_path}`"
            )

        else:

            st.caption(
                f"Host: `{db_cfg.host}:{db_cfg.port}`"
            )

            st.caption(
                f"Database: `{db_cfg.name}`"
            )

    except Exception as exc:

        st.error(
            f"Database config error: {exc}"
        )

    # --------------------------------------------------------
    # LLM
    # --------------------------------------------------------

    try:

        llm_cfg = load_llm_config()

        st.success(
            f"LLM: **{llm_cfg.provider}**"
        )

        st.caption(
            f"Model: `{llm_cfg.model or 'default'}`"
        )

    except Exception as exc:

        st.error(
            f"LLM config error: {exc}"
        )

    st.divider()

    # --------------------------------------------------------
    # Examples
    # --------------------------------------------------------

    st.markdown("### 💡 Examples")

    examples = [
        "Top 5 customers by total order amount",
        "How many orders per city?",
        "Average product price by category",
        "Orders with more than 1 item",
    ]

    for index, example in enumerate(examples):

        if st.button(
            example,
            use_container_width=True,
            key=f"example_{index}",
        ):

            st.session_state.pending_question = example
            st.rerun()

    st.divider()

    # --------------------------------------------------------
    # Clear chat
    # --------------------------------------------------------

    if st.button(
        "🗑️ Clear chat",
        use_container_width=True,
    ):

        st.session_state.history = []

        st.rerun()


# ============================================================
# HEADER
# ============================================================

st.markdown(
    '<p class="app-title">🧠 AI Data Analyst</p>',
    unsafe_allow_html=True,
)

st.markdown(
    '<p class="app-subtitle">'
    'Ask your database a question in natural language. '
    'Press Enter to run it.'
    '</p>',
    unsafe_allow_html=True,
)


# ============================================================
# REPLAY HISTORY
# ============================================================

for turn in st.session_state.history:

    with st.chat_message("user"):
        st.write(turn["question"])

    with st.chat_message("assistant"):
        display_results(
            turn["result"],
            turn.get("elapsed"),
        )


# ============================================================
# PENDING EXAMPLE
# ============================================================

pending = st.session_state.pop(
    "pending_question",
    None,
)


# ============================================================
# CHAT INPUT
# ============================================================

typed_question = st.chat_input(
    "Ask a question about your data..."
)


question = pending or typed_question


# ============================================================
# RUN QUERY
# ============================================================

if question:

    question = question.strip()

    if question:

        # ----------------------------------------------------
        # User message
        # ----------------------------------------------------

        with st.chat_message("user"):

            st.write(question)

        # ----------------------------------------------------
        # AI response
        # ----------------------------------------------------

        with st.chat_message("assistant"):

            start_time = time.perf_counter()

            with st.spinner(
                "Reading schema and generating SQL..."
            ):

                try:

                    result = get_data_from_database(
                        question
                    )

                except Exception as exc:

                    st.error(
                        f"Unexpected error: {exc}"
                    )

                    result = None

            elapsed = (
                time.perf_counter()
                - start_time
            )

            if result is not None:

                display_results(
                    result,
                    elapsed=elapsed,
                )

                # ------------------------------------------------
                # Save history
                # ------------------------------------------------

                st.session_state.history.append(
                    {
                        "question": question,
                        "result": result,
                        "elapsed": elapsed,
                    }
                )