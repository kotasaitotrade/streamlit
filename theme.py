"""
和モダン・クラフト UIテーマ
- 配色: 未漂白生成り、深焦茶、生漆朱、金茶
- タイポ: Klee One (本文・手書き風) + Yuji Mai (見出し・楷書)
- 質感: 紙のような柔らかい背景、控えめな影、緊張感のない余白
"""
import streamlit as st


_THEME_CSS = """
<style>
/* ─── Web Fonts ─────────────────────────────── */
@import url('https://fonts.googleapis.com/css2?family=Klee+One:wght@400;600&family=Yuji+Mai&family=Noto+Sans+Mono+CJK+JP&display=swap');

/* ─── Color Tokens ──────────────────────────── */
:root {
  --paper:       #FAF6EE;   /* 未漂白生成り（背景） */
  --paper-deep:  #F3EDDF;   /* 一段濃い生成り */
  --ink:         #2D241A;   /* 焦茶墨色（本文） */
  --ink-soft:    #6B5947;   /* 淡墨（補助テキスト） */
  --ink-faint:   #A89683;   /* ごく薄い茶 */
  --vermilion:   #B5443E;   /* 朱赤・生漆 */
  --vermilion-deep: #8E2F2A;
  --kincha:      #B8923C;   /* 金茶 */
  --moss:        #6A7F4F;   /* 苔色（継続中バッジ用） */
  --border:      #E0D3BB;   /* 薄ベージュ罫線 */
  --border-soft: #EEE5D2;
  --shadow:      0 1px 0 rgba(0,0,0,0.02), 0 8px 24px -16px rgba(45,36,26,0.18);
}

/* ─── App Background: subtle paper texture ─── */
[data-testid="stAppViewContainer"], .main, .stApp {
  background-color: var(--paper) !important;
  background-image:
    radial-gradient(circle at 18% 22%, rgba(184,146,60,0.04) 0%, transparent 32%),
    radial-gradient(circle at 82% 78%, rgba(181,68,62,0.03) 0%, transparent 30%),
    repeating-linear-gradient(
      45deg,
      rgba(45,36,26,0.012) 0px, rgba(45,36,26,0.012) 1px,
      transparent 1px, transparent 4px
    );
  color: var(--ink);
}

/* ─── Typography ────────────────────────────── */
html, body, [class*="css"], .stMarkdown, .stText, p, span, div, label, input, textarea, button {
  font-family: 'Klee One', 'Hiragino Mincho ProN', 'Yu Mincho', serif !important;
  color: var(--ink);
}

h1, h2, h3, h4, h5, h6, .stMarkdown h1, .stMarkdown h2, .stMarkdown h3 {
  font-family: 'Yuji Mai', 'Klee One', serif !important;
  color: var(--ink) !important;
  font-weight: 400 !important;
  letter-spacing: 0.04em;
}

/* Numbers / IDs in mono */
[data-testid="stMetricValue"], [class*="dataframe"] td:has(> div > span:not(:has(*))) {
  font-family: 'Noto Sans Mono CJK JP', 'JetBrains Mono', ui-monospace, monospace !important;
}

/* ─── Sidebar ───────────────────────────────── */
[data-testid="stSidebar"] {
  background-color: var(--paper-deep) !important;
  border-right: 1px solid var(--border);
}
[data-testid="stSidebar"] * {
  color: var(--ink);
}
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] strong {
  color: var(--vermilion);
  letter-spacing: 0.08em;
}

/* Sidebar radio - menu look */
[data-testid="stSidebar"] [role="radiogroup"] label {
  padding: 0.4rem 0.6rem;
  margin: 0.1rem 0;
  border-radius: 4px;
  transition: background 0.15s;
  font-family: 'Klee One', serif !important;
  font-size: 0.98rem;
}
[data-testid="stSidebar"] [role="radiogroup"] label:hover {
  background: rgba(184,146,60,0.10);
}

/* ─── Header (top app bar) ──────────────────── */
[data-testid="stHeader"] {
  background-color: transparent !important;
  backdrop-filter: blur(8px);
}

/* ─── Buttons ───────────────────────────────── */
.stButton > button, [data-testid="stFormSubmitButton"] > button {
  background: var(--paper) !important;
  color: var(--ink) !important;
  border: 1px solid var(--ink) !important;
  border-radius: 2px !important;
  font-family: 'Klee One', serif !important;
  font-weight: 600 !important;
  padding: 0.45rem 1.1rem !important;
  letter-spacing: 0.08em;
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
}

/* ─── Inputs ────────────────────────────────── */
.stTextInput input, .stTextArea textarea, .stNumberInput input, .stSelectbox [data-baseweb="select"] > div {
  background: var(--paper) !important;
  border: 1px solid var(--border) !important;
  border-radius: 2px !important;
  color: var(--ink) !important;
  font-family: 'Klee One', serif !important;
}
.stTextInput input:focus, .stTextArea textarea:focus, .stNumberInput input:focus {
  border-color: var(--vermilion) !important;
  box-shadow: 0 0 0 1px var(--vermilion) !important;
}

/* ─── Metrics ───────────────────────────────── */
[data-testid="stMetric"] {
  background: var(--paper) !important;
  border: 1px solid var(--border);
  border-radius: 2px;
  padding: 0.8rem 1rem;
  box-shadow: var(--shadow);
}
[data-testid="stMetricLabel"] {
  color: var(--ink-soft) !important;
  font-size: 0.78rem !important;
  letter-spacing: 0.08em;
  text-transform: none;
}
[data-testid="stMetricValue"] {
  color: var(--ink) !important;
  font-size: 1.6rem !important;
  font-weight: 600 !important;
}

/* ─── Expanders ─────────────────────────────── */
[data-testid="stExpander"] {
  background: var(--paper) !important;
  border: 1px solid var(--border) !important;
  border-radius: 2px !important;
  margin-bottom: 0.4rem;
  box-shadow: var(--shadow);
}
[data-testid="stExpander"] summary {
  padding: 0.7rem 1rem;
  font-family: 'Klee One', serif !important;
  font-weight: 600;
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
  font-family: 'Klee One', serif !important;
  letter-spacing: 0.06em;
  color: var(--ink-soft) !important;
}
[data-baseweb="tab"][aria-selected="true"] {
  color: var(--vermilion) !important;
  border-bottom: 2px solid var(--vermilion) !important;
}

/* ─── Dataframes / data_editor ─────────────── */
[data-testid="stDataFrame"], [data-testid="stDataEditor"] {
  border: 1px solid var(--border) !important;
  border-radius: 2px !important;
  background: var(--paper) !important;
}

/* ─── Dividers ──────────────────────────────── */
hr {
  border: none !important;
  border-top: 1px dashed var(--border) !important;
  margin: 1.2rem 0 !important;
}

/* ─── Alerts ────────────────────────────────── */
[data-testid="stAlert"] {
  border-radius: 2px !important;
  border-left: 3px solid var(--vermilion) !important;
  background: rgba(181,68,62,0.06) !important;
  color: var(--ink) !important;
}

/* ─── Checkboxes ────────────────────────────── */
[data-testid="stCheckbox"] label {
  font-family: 'Klee One', serif !important;
  color: var(--ink) !important;
}

/* ─── Captions ──────────────────────────────── */
[data-testid="stCaptionContainer"], .stCaption, small {
  color: var(--ink-soft) !important;
  font-style: normal;
}

/* ─── Subheaders/page titles with brush feel ── */
.stMarkdown h2, .stMarkdown h3 {
  position: relative;
  padding-left: 0.6rem;
}
.stMarkdown h2::before, .stMarkdown h3::before {
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
