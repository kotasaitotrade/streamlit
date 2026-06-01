"""
和モダン・クラフト UIテーマ
- 配色: 未漂白生成り、深焦茶、生漆朱、金茶
- タイポ: Klee One (本文) + Yuji Mai (見出し)
- 注意: Streamlit の Material Symbols アイコンフォントを壊さないよう、対象セレクタを限定
"""
import streamlit as st


_THEME_CSS = """
<style>
/* ─── Web Fonts ─────────────────────────────── */
@import url('https://fonts.googleapis.com/css2?family=Klee+One:wght@400;600&family=Yuji+Mai&display=swap');

/* ─── Color Tokens ──────────────────────────── */
:root {
  --paper:       #FAF6EE;
  --paper-deep:  #F3EDDF;
  --ink:         #2D241A;
  --ink-soft:    #6B5947;
  --ink-faint:   #A89683;
  --vermilion:   #B5443E;
  --vermilion-deep: #8E2F2A;
  --kincha:      #B8923C;
  --moss:        #6A7F4F;
  --border:      #E0D3BB;
  --border-soft: #EEE5D2;
  --shadow:      0 1px 0 rgba(0,0,0,0.02), 0 8px 24px -16px rgba(45,36,26,0.18);
}

/* ─── App Background ────────────────────────── */
[data-testid="stAppViewContainer"], .main, .stApp {
  background-color: var(--paper) !important;
}

/* ─── Typography: Streamlit固有のテキスト要素のみに適用 ─── */
/* Material Symbols / Material Icons は除外 */
[data-testid="stMarkdownContainer"],
[data-testid="stMarkdownContainer"] p,
[data-testid="stMarkdownContainer"] li,
[data-testid="stText"],
[data-testid="stCaptionContainer"],
.stMarkdown p,
.stMarkdown li,
[data-testid="stMetricLabel"] *,
[data-testid="stMetricValue"],
[data-testid="stMetricDelta"],
[data-testid="stExpander"] summary,
[data-testid="stTextInput"] label,
[data-testid="stTextArea"] label,
[data-testid="stSelectbox"] label,
[data-testid="stNumberInput"] label,
[data-testid="stCheckbox"] label,
[data-testid="stRadio"] label,
[data-testid="stDateInput"] label {
  font-family: 'Klee One', 'Hiragino Mincho ProN', 'Yu Mincho', serif !important;
}

/* 見出し */
[data-testid="stMarkdownContainer"] h1,
[data-testid="stMarkdownContainer"] h2,
[data-testid="stMarkdownContainer"] h3,
[data-testid="stMarkdownContainer"] h4,
[data-testid="stHeading"] h1,
[data-testid="stHeading"] h2,
[data-testid="stHeading"] h3 {
  font-family: 'Yuji Mai', 'Klee One', 'Hiragino Mincho ProN', serif !important;
  color: var(--ink) !important;
  font-weight: 400 !important;
  letter-spacing: 0.04em;
}

/* ─── Body text color ──────────────────────── */
[data-testid="stMarkdownContainer"], .stMarkdown {
  color: var(--ink);
}

/* ─── Sidebar ───────────────────────────────── */
[data-testid="stSidebar"] {
  background-color: var(--paper-deep) !important;
  border-right: 1px solid var(--border);
}
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] strong {
  color: var(--vermilion);
  letter-spacing: 0.04em;
}

/* Sidebar radio - menu look */
[data-testid="stSidebar"] [role="radiogroup"] label {
  padding: 0.3rem 0.4rem;
  margin: 0.1rem 0;
  border-radius: 3px;
  transition: background 0.15s;
}
[data-testid="stSidebar"] [role="radiogroup"] label:hover {
  background: rgba(184,146,60,0.10);
}

/* ─── Header ────────────────────────────────── */
[data-testid="stHeader"] {
  background-color: transparent !important;
}

/* ─── Buttons ───────────────────────────────── */
.stButton > button, [data-testid="stFormSubmitButton"] > button {
  background: var(--paper) !important;
  color: var(--ink) !important;
  border: 1px solid var(--ink) !important;
  border-radius: 2px !important;
  font-family: 'Klee One', 'Hiragino Mincho ProN', serif !important;
  font-weight: 600 !important;
  padding: 0.35rem 0.9rem !important;
  letter-spacing: 0.04em;
  box-shadow: 2px 2px 0 var(--ink) !important;
  transition: transform 0.08s, box-shadow 0.08s;
}
.stButton > button:hover, [data-testid="stFormSubmitButton"] > button:hover {
  transform: translate(1px, 1px);
  box-shadow: 1px 1px 0 var(--ink) !important;
  background: var(--paper-deep) !important;
  color: var(--ink) !important;
  border-color: var(--ink) !important;
}
.stButton > button[kind="primary"], [data-testid="stFormSubmitButton"] > button[kind="primary"] {
  background: var(--vermilion) !important;
  color: var(--paper) !important;
  border-color: var(--vermilion-deep) !important;
  box-shadow: 2px 2px 0 var(--vermilion-deep) !important;
}
.stButton > button[kind="primary"]:hover {
  box-shadow: 1px 1px 0 var(--vermilion-deep) !important;
  background: var(--vermilion-deep) !important;
  color: var(--paper) !important;
}

/* ─── Inputs ────────────────────────────────── */
[data-testid="stTextInput"] input,
[data-testid="stTextArea"] textarea,
[data-testid="stNumberInput"] input,
[data-testid="stSelectbox"] [data-baseweb="select"] > div {
  background: var(--paper) !important;
  border: 1px solid var(--border) !important;
  border-radius: 2px !important;
  color: var(--ink) !important;
  font-family: 'Klee One', 'Hiragino Mincho ProN', serif !important;
}
[data-testid="stTextInput"] input:focus,
[data-testid="stNumberInput"] input:focus {
  border-color: var(--vermilion) !important;
  box-shadow: 0 0 0 1px var(--vermilion) !important;
}

/* ─── Metrics ───────────────────────────────── */
[data-testid="stMetric"] {
  background: var(--paper) !important;
  border: 1px solid var(--border);
  border-radius: 2px;
  padding: 0.7rem 0.9rem;
  box-shadow: var(--shadow);
}
[data-testid="stMetricLabel"] {
  color: var(--ink-soft) !important;
  font-size: 0.78rem !important;
  letter-spacing: 0.04em;
}
[data-testid="stMetricValue"] {
  color: var(--ink) !important;
  font-weight: 600 !important;
}

/* ─── Expanders ─────────────────────────────── */
[data-testid="stExpander"] {
  background: var(--paper) !important;
  border: 1px solid var(--border) !important;
  border-radius: 2px !important;
  margin-bottom: 0.3rem;
}
[data-testid="stExpander"] summary {
  padding: 0.6rem 0.9rem;
  font-weight: 600;
  color: var(--ink) !important;
}
[data-testid="stExpander"] summary:hover {
  background: var(--paper-deep) !important;
}

/* ─── Tabs ──────────────────────────────────── */
[data-baseweb="tab-list"] {
  border-bottom: 1px solid var(--border) !important;
  gap: 1rem !important;
  background: transparent !important;
}
[data-baseweb="tab"] {
  background: transparent !important;
  font-family: 'Klee One', 'Hiragino Mincho ProN', serif !important;
  color: var(--ink-soft) !important;
}
[data-baseweb="tab"][aria-selected="true"] {
  color: var(--vermilion) !important;
  border-bottom-color: var(--vermilion) !important;
}

/* ─── Dataframes ────────────────────────────── */
[data-testid="stDataFrame"], [data-testid="stDataEditor"] {
  border: 1px solid var(--border) !important;
  border-radius: 2px !important;
}

/* ─── Dividers ──────────────────────────────── */
hr {
  border: none !important;
  border-top: 1px dashed var(--border) !important;
  margin: 1rem 0 !important;
}

/* ─── Alerts ────────────────────────────────── */
[data-testid="stAlert"] {
  border-radius: 2px !important;
  border-left: 3px solid var(--vermilion) !important;
}

/* ─── Captions ──────────────────────────────── */
[data-testid="stCaptionContainer"], .stCaption {
  color: var(--ink-soft) !important;
}

/* ─── Headings with brush accent ───────────── */
[data-testid="stHeading"] h2, [data-testid="stHeading"] h3,
[data-testid="stMarkdownContainer"] h2, [data-testid="stMarkdownContainer"] h3 {
  position: relative;
  padding-left: 0.6rem;
}
[data-testid="stHeading"] h2::before, [data-testid="stHeading"] h3::before,
[data-testid="stMarkdownContainer"] h2::before, [data-testid="stMarkdownContainer"] h3::before {
  content: '';
  position: absolute;
  left: 0;
  top: 0.18em;
  bottom: 0.18em;
  width: 3px;
  background: var(--vermilion);
}
</style>
"""


def apply_theme():
    """ストリームリットアプリに和モダンテーマを適用"""
    st.markdown(_THEME_CSS, unsafe_allow_html=True)
