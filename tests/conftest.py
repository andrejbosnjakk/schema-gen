"""Tests never touch the developer's real settings, projects or log (the app's per-user folder)."""
import time
from types import SimpleNamespace

import pytest


@pytest.fixture(autouse=True)
def _schemagen_home(tmp_path_factory, monkeypatch):
    monkeypatch.setenv("SCHEMAGEN_HOME", str(tmp_path_factory.mktemp("schemagen-home")))


def run_export(c, wait=120, **body):
    """POST /api/export, wait for the job and answer like the old synchronous endpoint did: a response-like object whose json() is
    {folder, files, failed}; a refused request is returned as it is, a failed job has status 400 and the job's status as its json."""
    r = c.post("/api/export", json=body)
    if r.status_code != 202: return r
    t = time.time()
    while True:
        j = c.get(f"/api/export/{r.json()['job']}").json()
        if j["state"] != "running" or time.time() - t > wait: break
        time.sleep(0.05)
    if j["state"] == "done":
        out = dict(folder=j["folder"], files=j["files"], **({"failed": j["failed"]} if body.get("kind") == "drawings" else {}))
        return SimpleNamespace(status_code=200, json=lambda: out, text="")
    return SimpleNamespace(status_code=400, json=lambda: dict(error=j), text=str(j))
