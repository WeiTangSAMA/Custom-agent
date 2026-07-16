from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import httpx


PROJECT_ROOT = Path(__file__).resolve().parents[1]
API_URL = "http://127.0.0.1:8000"


def backend_is_ready(base_url: str = API_URL) -> bool:
    try:
        response = httpx.get(f"{base_url}/health", timeout=1.0)
        return response.status_code == 200
    except httpx.HTTPError:
        return False


def _hidden_process_flags() -> int:
    return subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


def launch() -> int:
    """Launch FastAPI when needed, then run Streamlit in the foreground."""
    api_process: subprocess.Popen[bytes] | None = None
    environment = os.environ.copy()
    environment.setdefault("AGENT_API_URL", API_URL)
    environment.setdefault("PYTHONUTF8", "1")

    if not backend_is_ready():
        api_process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "app.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                "8000",
            ],
            cwd=PROJECT_ROOT,
            env=environment,
            creationflags=_hidden_process_flags(),
        )
        for _ in range(40):
            if backend_is_ready():
                break
            if api_process.poll() is not None:
                raise RuntimeError("FastAPI failed to start. Check the terminal output above.")
            time.sleep(0.25)
        else:
            api_process.terminate()
            raise RuntimeError("FastAPI did not become ready within 10 seconds.")

    print("Project Mind is starting at http://127.0.0.1:8501")
    try:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "streamlit",
                "run",
                str(PROJECT_ROOT / "streamlit_app.py"),
                "--server.port",
                "8501",
                "--server.headless",
                "false",
            ],
            cwd=PROJECT_ROOT,
            env=environment,
            check=False,
        )
        return result.returncode
    finally:
        if api_process is not None and api_process.poll() is None:
            api_process.terminate()
            try:
                api_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                api_process.kill()

