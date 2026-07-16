from __future__ import annotations

from types import SimpleNamespace

from app import launcher


def test_launcher_uses_streamlit_run_when_backend_is_ready(monkeypatch) -> None:
    captured: dict[str, object] = {}
    monkeypatch.setattr(launcher, "backend_is_ready", lambda: True)

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(launcher.subprocess, "run", fake_run)
    assert launcher.launch() == 0
    assert captured["command"][1:4] == ["-m", "streamlit", "run"]
    assert "streamlit_app.py" in captured["command"][4]


def test_launcher_starts_and_stops_owned_api(monkeypatch) -> None:
    readiness = iter([False, True])
    monkeypatch.setattr(launcher, "backend_is_ready", lambda: next(readiness))
    state = {"terminated": False}

    class FakeProcess:
        def poll(self):
            return None

        def terminate(self):
            state["terminated"] = True

        def wait(self, timeout):
            return 0

    monkeypatch.setattr(launcher.subprocess, "Popen", lambda *args, **kwargs: FakeProcess())
    monkeypatch.setattr(
        launcher.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0),
    )
    assert launcher.launch() == 0
    assert state["terminated"] is True

