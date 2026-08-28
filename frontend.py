import html
import time
from dataclasses import dataclass, field

import pandas as pd
import streamlit as st

from app.config import load_db_config, load_llm_config
from app.pipeline import get_data_from_database


# ============================================================
# PAGE CONFIG
# ============================================================

st.set_page_config(
    page_title="NL2SQL",
    page_icon="🗄️",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ============================================================
# DESIGN SYSTEM
# ============================================================
# A small "data console" identity: a quiet paper background, an
# indigo accent (deliberately not the generic blue/red chart-lib
# default), and a monospace face reserved for anything that reads
# like a data value (row counts, timings, labels) so the numbers in
# this app always look like numbers, not decoration.

st.markdown(
    """
    <style>
        @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap');

        :root {
            --ink: #14161b;
            --muted: #6b6e76;
            --paper: #fafaf8;
            --surface: #ffffff;
            --line: #e4e3de;
            --accent: #5b4fe0;
            --accent-strong: #4638d1;
            --accent-soft: #eeecfd;
            --accent-line: #d9d5fa;
            --teal: #0fac86;
            --teal-soft: #e4f7f1;
            --mint: #0f9d6b;
            --mint-soft: #e8f7f1;
            --coral: #dc5b4d;
            --coral-soft: #fbeceA;
            --console-bg: #15161f;
            --console-line: #262835;
            --console-text: #c9cbd6;
            --console-muted: #8b8fa3;
            --console-accent: #9d8ffb;
            --console-mint: #34d8a7;
            --console-coral: #ff8f84;
        }

        @media (prefers-reduced-motion: reduce) {
            *, *::before, *::after {
                animation-duration: 0.001ms !important;
                animation-iteration-count: 1 !important;
                transition-duration: 0.001ms !important;
            }
        }

        html, body, [data-testid="stAppViewContainer"] {
            background: var(--paper);
            color: var(--ink);
            font-family: 'IBM Plex Sans', sans-serif;
        }

        .main .block-container {
            max-width: 880px;
            padding-top: 2.25rem;
            padding-bottom: 3rem;
        }

        code, .stCode, [data-testid="stMetricValue"] {
            font-family: 'IBM Plex Mono', monospace !important;
        }

        /* -------- Header -------- */
        .app-eyebrow {
            font-family: 'IBM Plex Mono', monospace;
            font-size: 11.5px;
            font-weight: 500;
            letter-spacing: 0.14em;
            text-transform: uppercase;
            color: var(--accent);
            margin-bottom: 8px;
        }

        .app-eyebrow .cursor {
            display: inline-block;
            margin-left: 2px;
            color: var(--accent);
            animation: blink 1.1s steps(1) infinite;
        }

        @keyframes blink {
            50% { opacity: 0; }
        }

        .app-accent-rule {
            width: 46px;
            height: 3px;
            border-radius: 999px;
            margin: 10px 0 14px;
            background: linear-gradient(90deg, var(--accent), var(--teal));
        }

        .app-title {
            font-size: 2.1rem;
            font-weight: 700;
            margin-bottom: 2px;
            letter-spacing: -0.01em;
            background: linear-gradient(100deg, var(--ink) 45%, var(--accent-strong) 130%);
            -webkit-background-clip: text;
            background-clip: text;
            color: transparent;
            display: inline-block;
        }

        .app-subtitle {
            color: var(--muted);
            margin-top: 4px;
            margin-bottom: 1.75rem;
            font-size: 15px;
        }

        /* -------- Sidebar (dark "console" panel) -------- */
        section[data-testid="stSidebar"] {
            background: var(--console-bg);
            border-right: 1px solid var(--console-line);
        }

        section[data-testid="stSidebar"] p,
        section[data-testid="stSidebar"] span,
        section[data-testid="stSidebar"] label,
        section[data-testid="stSidebar"] .stMarkdown {
            color: var(--console-text);
        }

        section[data-testid="stSidebar"] small,
        section[data-testid="stSidebar"] [data-testid="stCaptionContainer"] {
            color: var(--console-muted) !important;
        }

        section[data-testid="stSidebar"] code {
            background: rgba(255, 255, 255, 0.07);
            color: var(--console-text);
        }

        section[data-testid="stSidebar"] hr {
            border-color: var(--console-line);
        }

        .eyebrow {
            font-family: 'IBM Plex Mono', monospace;
            font-size: 10.5px;
            font-weight: 600;
            letter-spacing: 0.12em;
            text-transform: uppercase;
            color: var(--console-muted);
            margin: 4px 0 10px;
        }

        /* An eyebrow used in the light main-content area (e.g. above
           the quick-visualization block) needs the light-mode muted
           tone instead of the sidebar's light-on-dark tone. */
        .main .eyebrow {
            color: var(--muted);
        }

        section[data-testid="stSidebar"] div[data-testid="stAlert"] {
            border-radius: 8px;
            font-size: 13.5px;
            border: 1px solid transparent;
        }

        /* Recolor Streamlit's native alert boxes to match the palette
           instead of the default green/red, so status reads as part
           of the same system rather than a bolted-on library default.
           Sidebar alerts get dark-appropriate translucent tints. */
        section[data-testid="stSidebar"] div[data-testid="stAlertContentSuccess"] { color: var(--console-mint) !important; }
        section[data-testid="stSidebar"] div[data-testid="stAlert"]:has(div[data-testid="stAlertContentSuccess"]) {
            background: rgba(52, 216, 167, 0.12);
            border-color: rgba(52, 216, 167, 0.22);
        }
        section[data-testid="stSidebar"] div[data-testid="stAlertContentError"] { color: var(--console-coral) !important; }
        section[data-testid="stSidebar"] div[data-testid="stAlert"]:has(div[data-testid="stAlertContentError"]) {
            background: rgba(255, 143, 132, 0.12);
            border-color: rgba(255, 143, 132, 0.22);
        }

        div[data-testid="stAlertContentInfo"] { color: var(--accent); }
        div[data-testid="stAlert"]:has(div[data-testid="stAlertContentInfo"]) {
            background: var(--accent-soft);
        }
        div[data-testid="stAlertContentError"] { color: var(--coral); }
        .main div[data-testid="stAlert"]:has(div[data-testid="stAlertContentError"]) {
            background: var(--coral-soft);
        }

        /* -------- Buttons (sidebar: examples + clear chat) -------- */
        .stButton > button {
            position: relative;
            overflow: hidden;
            border-radius: 8px;
            border: 1px solid var(--console-line);
            background: transparent;
            color: var(--console-text);
            font-size: 13.5px;
            text-align: left;
            justify-content: flex-start;
            padding-left: 16px;
            transition: border-color 0.15s ease, background 0.15s ease, color 0.15s ease;
        }

        .stButton > button::before {
            content: "";
            position: absolute;
            left: 0;
            top: 0;
            bottom: 0;
            width: 3px;
            background: var(--console-accent);
            transform: scaleY(0);
            transition: transform 0.18s ease;
        }

        .stButton > button:hover {
            border-color: var(--console-accent);
            background: rgba(157, 143, 251, 0.1);
            color: #ffffff;
        }

        .stButton > button:hover::before {
            transform: scaleY(1);
        }

        div[data-testid="stDownloadButton"] > button {
            border-radius: 8px;
            border: 1px solid var(--line);
            transition: border-color 0.15s ease, color 0.15s ease;
        }

        div[data-testid="stDownloadButton"] > button:hover {
            border-color: var(--accent);
            color: var(--accent);
        }

        /* -------- Chat -------- */
        div[data-testid="stChatMessage"] {
            padding-top: 0.3rem;
            padding-bottom: 0.3rem;
        }

        div[data-testid="stChatMessageContent"] {
            font-size: 15px;
        }

        div[data-testid="stChatMessageContent"] p {
            line-height: 1.55;
        }

        /* Differentiate user vs. assistant turns: a tinted "command"
           bubble for what the person typed, a quiet card for what the
           system answered — read at a glance without needing to check
           who the avatar belongs to. */
        div[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) div[data-testid="stChatMessageContent"] {
            background: var(--accent-soft);
            border: 1px solid var(--accent-line);
            border-radius: 14px;
            padding: 10px 16px;
        }

        div[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarAssistant"]) div[data-testid="stChatMessageContent"] {
            background: var(--surface);
            border: 1px solid var(--line);
            border-radius: 14px;
            padding: 12px 16px;
        }

        [data-testid="stChatMessageAvatarUser"] {
            background: var(--ink) !important;
            color: #ffffff !important;
        }

        [data-testid="stChatMessageAvatarAssistant"] {
            background: var(--accent) !important;
            color: #ffffff !important;
        }

        /* -------- Empty state -------- */
        .empty-state {
            text-align: center;
            padding: 56px 20px;
            color: var(--muted);
            border: 1px dashed var(--line);
            border-radius: 14px;
            margin-top: 8px;
        }

        .empty-state-icon {
            font-size: 26px;
            color: var(--accent);
            margin-bottom: 12px;
        }

        .empty-state-title {
            font-weight: 600;
            color: var(--ink);
            font-size: 15px;
            margin-bottom: 4px;
        }

        .empty-state-text {
            font-size: 13.5px;
        }

        /* -------- Tabs -------- */
        .stTabs [data-baseweb="tab-list"] {
            gap: 4px;
            border-bottom: 1px solid var(--line);
        }

        .stTabs [data-baseweb="tab"] {
            font-size: 13.5px;
            color: var(--muted);
        }

        .stTabs [aria-selected="true"] {
            color: var(--ink) !important;
        }

        .stTabs [data-baseweb="tab-highlight"] {
            background-color: var(--accent) !important;
        }

        /* -------- Dataframe -------- */
        div[data-testid="stDataFrame"] {
            border-radius: 8px;
            border: 1px solid var(--line);
        }

        /* -------- Record strip (signature element) --------
           A single monospace line standing in for what would
           otherwise be scattered captions and metric tiles: a
           status dot plus tabular values, styled like one entry
           in a query log rather than a dashboard widget. */
        .record-strip {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            padding: 5px 12px;
            border-radius: 999px;
            background: var(--surface);
            border: 1px solid var(--line);
            margin: 2px 0 4px;
        }

        .record-strip.subtle {
            background: var(--accent-soft);
            border-color: var(--accent-line);
        }

        .record-dot {
            width: 7px;
            height: 7px;
            border-radius: 50%;
            background: var(--teal);
            flex-shrink: 0;
            animation: dot-pulse 2.2s ease-in-out infinite;
        }

        @keyframes dot-pulse {
            0%, 100% { box-shadow: 0 0 0 0 rgba(15, 172, 134, 0.35); }
            50% { box-shadow: 0 0 0 4px rgba(15, 172, 134, 0); }
        }

        .record-text {
            font-family: 'IBM Plex Mono', monospace;
            font-size: 12.5px;
            color: var(--ink);
            font-variant-numeric: tabular-nums;
        }

        /* -------- Quick chart: bar mode -------- */
        .quick-chart {
            width: 100%;
            max-width: 760px;
            margin-top: 10px;
        }

        .chart-note {
            font-family: 'IBM Plex Mono', monospace;
            font-size: 11.5px;
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
            height: 20px;
            background: #f1f0ec;
            border-radius: 5px;
            overflow: hidden;
            position: relative;
        }

        .chart-bar {
            height: 100%;
            border-radius: 5px;
            background: linear-gradient(90deg, #7c74f1, var(--accent));
            transition: width 0.4s ease;
        }

        .chart-bar.negative {
            background: linear-gradient(90deg, #ef8177, var(--coral));
        }

        .chart-row:hover .chart-track {
            background: var(--accent-soft);
        }

        .chart-value {
            width: 78px;
            min-width: 78px;
            font-family: 'IBM Plex Mono', monospace;
            font-size: 12.5px;
            color: #374151;
            font-weight: 500;
            font-variant-numeric: tabular-nums;
        }

        .chart-value.negative { color: var(--coral); }

        /* -------- Quick chart: single-value stat card -------- */
        .stat-card {
            position: relative;
            overflow: hidden;
            max-width: 340px;
            padding: 22px 24px 20px;
            border: 1px solid var(--line);
            border-radius: 14px;
            background: var(--surface);
        }

        .stat-card-glow {
            position: absolute;
            top: -46px;
            right: -46px;
            width: 150px;
            height: 150px;
            border-radius: 50%;
            background: radial-gradient(circle, rgba(79, 70, 229, 0.12), transparent 70%);
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
            width: 36px;
            height: 36px;
            flex-shrink: 0;
            border-radius: 9px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 16px;
            background: var(--accent-soft);
            border: 1px solid var(--accent-line);
        }

        .stat-chip {
            font-family: 'IBM Plex Mono', monospace;
            font-size: 10.5px;
            font-weight: 600;
            letter-spacing: 0.02em;
            color: var(--accent);
            background: var(--accent-soft);
            border: 1px solid var(--accent-line);
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
            font-family: 'IBM Plex Mono', monospace;
            font-size: 32px;
            font-weight: 600;
            color: var(--ink);
            letter-spacing: -0.01em;
            font-variant-numeric: tabular-nums;
            line-height: 1.1;
        }

        .stat-metric-label {
            position: relative;
            z-index: 1;
            margin-top: 6px;
            font-size: 11.5px;
            font-weight: 600;
            color: var(--muted);
            text-transform: uppercase;
            letter-spacing: 0.06em;
        }

        /* -------- Quick chart: trend mode (time-series) -------- */
        .trend-chart {
            width: 100%;
            max-width: 760px;
            margin-top: 10px;
            border: 1px solid var(--line);
            border-radius: 10px;
            padding: 14px 16px 10px;
            background: var(--surface);
        }

        .trend-header {
            display: flex;
            justify-content: space-between;
            align-items: baseline;
            margin-bottom: 6px;
        }

        .trend-latest-label {
            font-family: 'IBM Plex Mono', monospace;
            font-size: 11.5px;
            color: var(--muted);
        }

        .trend-latest-value {
            font-family: 'IBM Plex Mono', monospace;
            font-size: 19px;
            font-weight: 600;
            color: var(--ink);
            font-variant-numeric: tabular-nums;
        }

        .trend-delta {
            font-family: 'IBM Plex Mono', monospace;
            font-size: 12px;
            font-weight: 600;
            margin-left: 8px;
        }

        .trend-delta.up { color: var(--mint); }
        .trend-delta.down { color: var(--coral); }
        .trend-delta.flat { color: var(--muted); }

        .trend-axis-label {
            font-family: 'IBM Plex Mono', monospace;
            font-size: 10.5px;
            color: #9ca3af;
        }
    </style>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# FALLBACK RESULT (for exceptions raised outside the pipeline)
# ============================================================

@dataclass
class _ErrorResult:
    """Mirrors the shape of whatever get_data_from_database() normally
    returns (success/error/sql/rows/columns), so a Python exception can
    flow through the exact same display_results()/history path instead
    of being handled as a special case that then vanishes on rerun."""

    success: bool = False
    error: str = ""
    sql: str = None
    rows: list = field(default_factory=list)
    columns: list = field(default_factory=list)


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

def _flatten_html(html_str: str) -> str:
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
    lines = [line.strip() for line in html_str.strip().splitlines()]
    return " ".join(line for line in lines if line)


def _escape(value) -> str:
    """HTML-escape any value pulled from query results before it gets
    interpolated into an f-string destined for unsafe_allow_html=True.

    Column names and cell values come from the user's database via
    LLM-generated SQL, so they're not trusted input. Without this, a
    value containing a stray '<' or '"' can break out of an attribute
    or tag and inject arbitrary HTML/JS into the page."""
    return html.escape(str(value), quote=True)


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


def render_record_strip(text_value: str, subtle: bool = False):
    """Signature status line: a single monospace strip with a status
    dot, used in place of scattered captions/metric tiles so timing
    and row/column counts always read as one continuous log entry
    rather than disconnected dashboard widgets."""
    css_class = "record-strip subtle" if subtle else "record-strip"
    st.markdown(
        _flatten_html(
            f"""
            <div class="{css_class}">
                <span class="record-dot"></span>
                <span class="record-text">{_escape(text_value)}</span>
            </div>
            """
        ),
        unsafe_allow_html=True,
    )


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
        label = _escape(label)
        value = chart_df.iloc[0][value_column]
        icon = _pick_metric_icon(value_column)
        metric_label = _escape(_prettify_column_name(value_column))
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
        label = _escape(label)

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
        note = f'<div class="chart-note">Showing top {shown} of {total_rows} rows, ranked by {_escape(value_column)}.</div>'

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

    # Duplicate timestamps (e.g. two rows for the same day) would draw a
    # jagged, misleading line — collapse them the same way the bar chart
    # collapses duplicate labels.
    if chart_df[label_column].duplicated().any():
        chart_df = (
            chart_df.groupby(label_column, as_index=False)
            .agg({value_column: "sum", "_parsed_date": "first"})
            .sort_values("_parsed_date")
        )

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

    value_column_safe = _escape(value_column)
    first_label_safe = _escape(labels[0])
    last_label_safe = _escape(labels[-1])

    svg = f"""
    <svg viewBox="0 0 {width} {height}" width="100%" height="{height}" preserveAspectRatio="none">
        <defs>
            <linearGradient id="trendFill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stop-color="#4f46e5" stop-opacity="0.16" />
                <stop offset="100%" stop-color="#4f46e5" stop-opacity="0" />
            </linearGradient>
        </defs>
        <line x1="{pad_x}" y1="{height - pad_y}" x2="{width - pad_x}" y2="{height - pad_y}"
              stroke="#e4e3de" stroke-width="1" />
        <path d="{area_path}" fill="url(#trendFill)" stroke="none" />
        <path d="{line_path}" fill="none" stroke="#4f46e5" stroke-width="2.5"
              stroke-linejoin="round" stroke-linecap="round" />
        <circle cx="{last_x:.1f}" cy="{last_y:.1f}" r="4" fill="#4f46e5" stroke="#ffffff" stroke-width="2" />
    </svg>
    """

    final_html = f"""
    <div class="trend-chart">
        <div class="trend-header">
            <div>
                <span class="trend-latest-value">{_format_number(latest_value)}</span>
                <span class="trend-delta {delta_class}">{delta_arrow} {_format_number(abs(delta))}</span>
            </div>
            <div class="trend-latest-label">{value_column_safe} · latest: {last_label_safe}</div>
        </div>
        {svg}
        <div style="display:flex; justify-content:space-between;">
            <span class="trend-axis-label">{first_label_safe}</span>
            <span class="trend-axis-label">{last_label_safe}</span>
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

def display_results(result, elapsed=None, key_suffix: str = "0"):
    """Display SQL, result table, record strip and small visualization.

    key_suffix must be unique per call site (e.g. the turn index in
    history) since this renders a download_button — a Streamlit widget
    that needs a stable, unique key when the same function runs more
    than once per script run (replaying history) or across reruns.
    """

    if not result.success:

        st.error(f"{result.error}")

        if result.sql:
            with st.expander("Generated SQL"):
                st.code(
                    result.sql,
                    language="sql",
                )

        return

    # --------------------------------------------------------
    # Tabs
    # --------------------------------------------------------

    tab_result, tab_sql = st.tabs(
        [
            "Result",
            "SQL",
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
        # Record strip — row/column count plus timing, as one
        # continuous log entry instead of separate metric tiles.
        # ----------------------------------------------------

        strip_parts = [f"{len(df):,} rows", f"{len(df.columns):,} cols"]
        if elapsed is not None:
            strip_parts.append(f"{elapsed:.2f}s")
        render_record_strip("  ·  ".join(strip_parts))

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
            label="Download CSV",
            data=csv_data,
            file_name="query_results.csv",
            mime="text/csv",
            key=f"download_{key_suffix}",
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
                st.markdown('<div class="eyebrow">Quick visualization</div>', unsafe_allow_html=True)

                # A single malformed row or unexpected dtype shouldn't
                # take down the whole result view — the table and
                # download button above are still useful on their own.
                try:
                    render_quick_chart(df)
                except Exception as exc:
                    st.caption(f"(Couldn't render a chart for this result: {exc})")


# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:

    st.markdown('<div class="eyebrow">Connection</div>', unsafe_allow_html=True)

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

    st.markdown('<div class="eyebrow">Try asking</div>', unsafe_allow_html=True)

    # Examples are generated from whatever tables are actually in the
    # connected database — never hardcoded — so they stay valid no
    # matter what schema this app is pointed at (local, remote,
    # different domain entirely).
    try:
        from app.db.schema_service import list_tables

        available_tables = list_tables()
        examples = [
            f"Show me the first 5 rows from {table}"
            for table in available_tables[:4]
        ] or ["Ask a question about your data"]

    except Exception:
        examples = ["Ask a question about your data"]

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
        "Clear chat",
        use_container_width=True,
    ):

        st.session_state.history = []

        st.rerun()


# ============================================================
# HEADER
# ============================================================

st.markdown(
    '<div class="app-eyebrow">natural language → sql<span class="cursor">_</span></div>',
    unsafe_allow_html=True,
)

st.markdown(
    '<p class="app-title">NL2SQL Engine</p>',
    unsafe_allow_html=True,
)

st.markdown(
    '<div class="app-accent-rule"></div>',
    unsafe_allow_html=True,
)

st.markdown(
    '<p class="app-subtitle">'
    'A schema-aware natural language to SQL system. '
    'Ask a question, see the generated query and results.'
    '</p>',
    unsafe_allow_html=True,
)


# ============================================================
# PENDING EXAMPLE + CHAT INPUT
# ============================================================
# Resolved before the replay/empty-state section below, even though
# st.chat_input always renders pinned to the bottom of the page
# regardless of call order — this just lets the empty state know
# whether a question is about to land this run.

pending = st.session_state.pop(
    "pending_question",
    None,
)

typed_question = st.chat_input(
    "Ask a question about your data..."
)

question = pending or typed_question


# ============================================================
# REPLAY HISTORY
# ============================================================
# Avatars double as a small piece of the identity: "❯" marks a typed
# command, "◆" marks the system's reply — the same shorthand a shell
# prompt uses, fitting for a tool that turns questions into SQL.

for turn_index, turn in enumerate(st.session_state.history):

    with st.chat_message("user", avatar="⌨️"):
        st.write(turn["question"])

    with st.chat_message("assistant", avatar="🔷"):
        display_results(
            turn["result"],
            turn.get("elapsed"),
            key_suffix=f"history_{turn_index}",
        )


# ============================================================
# EMPTY STATE
# ============================================================

if not st.session_state.history and not question:

    st.markdown(
        _flatten_html(
            """
            <div class="empty-state">
                <div class="empty-state-icon">🔷</div>
                <div class="empty-state-title">Nothing run yet</div>
                <div class="empty-state-text">
                    Try one of the examples in the sidebar, or ask your
                    own question below.
                </div>
            </div>
            """
        ),
        unsafe_allow_html=True,
    )


# ============================================================
# RUN QUERY
# ============================================================

if question:

    question = question.strip()

    if question:

        # ----------------------------------------------------
        # User message
        # ----------------------------------------------------

        with st.chat_message("user", avatar="⌨️"):

            st.write(question)

        # ----------------------------------------------------
        # AI response
        # ----------------------------------------------------

        with st.chat_message("assistant", avatar="🔷"):

            start_time = time.perf_counter()

            with st.spinner(
                "Reading schema and generating SQL..."
            ):

                try:

                    result = get_data_from_database(
                        question
                    )

                except Exception as exc:

                    # Wrap the exception in the same result shape the
                    # pipeline normally returns, so it flows through
                    # display_results() and gets saved to history like
                    # any other query instead of disappearing on the
                    # next rerun (e.g. clicking a sidebar example).
                    result = _ErrorResult(
                        error=f"Unexpected error: {exc}"
                    )

            elapsed = (
                time.perf_counter()
                - start_time
            )

            display_results(
                result,
                elapsed=elapsed,
                key_suffix=f"live_{len(st.session_state.history)}",
            )

            # ------------------------------------------------
            # Save history
            # -------------------------------------------------

            st.session_state.history.append(
                {
                    "question": question,
                    "result": result,
                    "elapsed": elapsed,
                }
            )
