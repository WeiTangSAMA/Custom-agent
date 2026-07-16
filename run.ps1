$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $Python)) {
    throw "Virtual environment not found. Run: python -m venv .venv; .\.venv\Scripts\python.exe -m pip install -e '.[dev]'"
}

& $Python (Join-Path $ProjectRoot "streamlit_app.py")
