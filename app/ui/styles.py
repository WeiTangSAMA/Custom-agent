APP_CSS = r"""
<style>
:root {
  --ui-bg: oklch(1 0 0);
  --ui-surface: oklch(0.965 0.006 40);
  --ui-surface-strong: oklch(0.925 0.012 40);
  --ui-ink: oklch(0.205 0.022 35);
  --ui-muted: oklch(0.46 0.025 35);
  --ui-primary: oklch(0.50 0.151 40);
  --ui-primary-hover: oklch(0.44 0.151 40);
  --ui-accent: oklch(0.38 0.095 205);
  --ui-success: oklch(0.43 0.105 145);
  --ui-warning: oklch(0.58 0.13 75);
  --ui-error: oklch(0.49 0.17 25);
  --ui-border: oklch(0.885 0.012 40);
  --ui-focus: oklch(0.62 0.12 40);
}

html, body, [class*="css"] {
  font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  color: var(--ui-ink);
}

[data-testid="stAppViewContainer"] {
  background: var(--ui-bg);
}

[data-testid="stSidebar"] {
  background: var(--ui-surface);
  border-right: 1px solid var(--ui-border);
}

[data-testid="stSidebar"] > div:first-child {
  padding-top: 1.3rem;
}

.block-container {
  max-width: 1120px;
  padding-top: 2.1rem;
  padding-bottom: 4rem;
}

h1, h2, h3 {
  color: var(--ui-ink);
  letter-spacing: -0.025em;
  text-wrap: balance;
}

h1 { font-size: 1.85rem !important; line-height: 1.2 !important; }
h2 { font-size: 1.35rem !important; }
h3 { font-size: 1.05rem !important; }
p, li { text-wrap: pretty; }

.app-brand {
  display: flex;
  align-items: center;
  gap: .7rem;
  margin: 0 0 1.2rem;
}

.app-mark {
  width: 2rem;
  height: 2rem;
  display: grid;
  place-items: center;
  border-radius: 9px;
  color: oklch(1 0 0);
  background: var(--ui-primary);
  font-weight: 750;
  font-size: .88rem;
}

.app-brand strong { display: block; line-height: 1.15; }
.app-brand span { display: block; color: var(--ui-muted); font-size: .78rem; margin-top: .14rem; }

.page-heading {
  margin-bottom: 1.5rem;
}

.page-heading p {
  color: var(--ui-muted);
  margin: .3rem 0 0;
  max-width: 68ch;
}

.status-line {
  display: flex;
  align-items: center;
  gap: .45rem;
  color: var(--ui-muted);
  font-size: .82rem;
  margin: .25rem 0 1rem;
}

.status-dot {
  width: .52rem;
  height: .52rem;
  border-radius: 999px;
  background: var(--ui-success);
}

.status-dot.offline { background: var(--ui-error); }
.status-dot.warning { background: var(--ui-warning); }

.metric-strip {
  display: flex;
  flex-wrap: wrap;
  gap: .55rem 1rem;
  padding: .75rem 0 1.05rem;
  border-bottom: 1px solid var(--ui-border);
  margin-bottom: 1.15rem;
  color: var(--ui-muted);
  font-size: .82rem;
}

.metric-strip strong { color: var(--ui-ink); font-variant-numeric: tabular-nums; }

.empty-state {
  padding: 2.5rem 1.25rem;
  text-align: center;
  border: 1px dashed var(--ui-border);
  border-radius: 14px;
  color: var(--ui-muted);
}

.empty-state strong {
  color: var(--ui-ink);
  display: block;
  margin-bottom: .35rem;
}

.source-chip {
  display: inline-flex;
  align-items: center;
  padding: .25rem .5rem;
  margin: .2rem .25rem .2rem 0;
  border-radius: 999px;
  background: oklch(0.93 0.025 205);
  color: var(--ui-accent);
  font-size: .78rem;
  font-weight: 620;
}

[data-testid="stChatMessage"] {
  border-radius: 14px;
  padding: .25rem .55rem;
}

[data-testid="stChatMessage"] p {
  line-height: 1.65;
  max-width: 75ch;
}

.stButton > button, .stDownloadButton > button {
  border-radius: 9px;
  min-height: 2.45rem;
  font-weight: 620;
  transition: background-color 180ms ease-out, border-color 180ms ease-out, color 180ms ease-out;
}

.stButton > button[kind="primary"] {
  background: var(--ui-primary);
  color: oklch(1 0 0);
  border: 0;
}

.stButton > button[kind="primary"]:hover {
  background: var(--ui-primary-hover);
  color: oklch(1 0 0);
}

.stButton > button:focus-visible,
input:focus-visible,
textarea:focus-visible {
  outline: 3px solid color-mix(in oklch, var(--ui-focus) 38%, transparent);
  outline-offset: 2px;
}

[data-baseweb="input"] > div,
[data-baseweb="textarea"] > div,
[data-baseweb="select"] > div,
[data-testid="stFileUploaderDropzone"] {
  border-radius: 10px;
}

[data-testid="stAlert"] { border-radius: 10px; }
[data-testid="stExpander"] { border-color: var(--ui-border); border-radius: 10px; }

@media (max-width: 700px) {
  .block-container { padding: 1.25rem 1rem 3rem; }
  h1 { font-size: 1.55rem !important; }
  .metric-strip { gap: .4rem .7rem; }
}

@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    scroll-behavior: auto !important;
    transition-duration: 0.01ms !important;
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
  }
}
</style>
"""

