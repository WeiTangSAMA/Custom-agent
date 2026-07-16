from __future__ import annotations

from app import launcher


def test_launcher_uses_streamlit_run_when_backend_is_ready(monkeypatch) -> None:
    captured: dict[str, object] = {}
    monkeypatch.setattr(launcher, "backend_is_ready", lambda: True)

    class CompletedProcess:
        def __init__(self, command, **kwargs):
            captured["command"] = command
            captured["kwargs"] = kwargs

        def poll(self):
            return 0

        def wait(self, timeout=None):
            return 0

    def fake_popen(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return CompletedProcess(command, **kwargs)

    monkeypatch.setattr(launcher.subprocess, "Popen", fake_popen)
    assert launcher.launch() == 0
    assert captured["command"][1:4] == ["-m", "streamlit", "run"]
    assert "streamlit_app.py" in captured["command"][4]


def test_launcher_starts_and_stops_owned_api(monkeypatch) -> None:
    readiness = iter([False, True])
    monkeypatch.setattr(launcher, "backend_is_ready", lambda: next(readiness))
    state = {"api_terminated": False}

    class APIProcess:
        def poll(self):
            return None

        def terminate(self):
            state["api_terminated"] = True

        def wait(self, timeout=None):
            return 0

    class UIProcess:
        def poll(self):
            return 0

        def wait(self, timeout=None):
            return 0

    processes = iter([APIProcess(), UIProcess()])
    monkeypatch.setattr(launcher.subprocess, "Popen", lambda *args, **kwargs: next(processes))
    assert launcher.launch() == 0
    assert state["api_terminated"] is True


def test_launcher_handles_keyboard_interrupt_without_traceback(monkeypatch) -> None:
    monkeypatch.setattr(launcher, "backend_is_ready", lambda: True)
    state = {"terminated": False}

    class InterruptedUIProcess:
        def poll(self):
            return None

        def terminate(self):
            state["terminated"] = True

        def wait(self, timeout=None):
            if timeout is None:
                raise KeyboardInterrupt
            return 0

    monkeypatch.setattr(
        launcher.subprocess,
        "Popen",
        lambda *args, **kwargs: InterruptedUIProcess(),
    )
    assert launcher.launch() == 0
    assert state["terminated"] is True
