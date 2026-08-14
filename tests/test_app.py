"""Tests for the Flask web UI's job handling, especially that multiple
searches can run concurrently (e.g. from separate browser tabs) instead of
being serialized behind a single global lock.
"""
from __future__ import annotations

import time
from unittest.mock import patch

import app as app_module


def _stub_pipeline_factory(delay: float):
    """Return a run_pipeline stand-in that logs progress and blocks briefly,
    so we can observe multiple jobs overlapping in time without hitting the
    network."""

    def stub(config, **kwargs):
        on_progress = kwargs.get("on_progress")
        if on_progress:
            on_progress(f"searching for {config.make} {config.model}...")
        time.sleep(delay)
        if on_progress:
            on_progress("done")
        return [], "reports/fake.md"

    return stub


def test_run_endpoint_returns_a_job_id():
    client = app_module.app.test_client()
    with patch.object(app_module, "run_pipeline", _stub_pipeline_factory(0)):
        resp = client.post("/run", data={"make": "Honda", "model": "Pilot"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert "job_id" in data and data["job_id"]


def test_two_concurrent_run_calls_get_distinct_jobs_and_do_not_block():
    client = app_module.app.test_client()
    with patch.object(app_module, "run_pipeline", _stub_pipeline_factory(0.3)):
        resp_a = client.post("/run", data={"make": "Honda", "model": "Pilot"})
        resp_b = client.post("/run", data={"make": "Toyota", "model": "4Runner"})

        assert resp_a.status_code == 200
        assert resp_b.status_code == 200
        job_a = resp_a.get_json()["job_id"]
        job_b = resp_b.get_json()["job_id"]
        assert job_a != job_b

        # Both should still be running shortly after starting -- if they were
        # serialized behind a single lock, the second call would either be
        # rejected (409) or not start until the first finished.
        status_a = client.get(f"/status?job_id={job_a}").get_json()
        status_b = client.get(f"/status?job_id={job_b}").get_json()
        assert status_a["running"] is True
        assert status_b["running"] is True

        # Wait for both to finish and confirm they completed without error.
        for _ in range(20):
            time.sleep(0.1)
            status_a = client.get(f"/status?job_id={job_a}").get_json()
            status_b = client.get(f"/status?job_id={job_b}").get_json()
            if not status_a["running"] and not status_b["running"]:
                break
        assert status_a["running"] is False
        assert status_b["running"] is False
        assert status_a["error"] is None
        assert status_b["error"] is None


def test_status_requires_job_id():
    client = app_module.app.test_client()
    resp = client.get("/status")
    assert resp.status_code == 400


def test_status_unknown_job_id_returns_404():
    client = app_module.app.test_client()
    resp = client.get("/status?job_id=does-not-exist")
    assert resp.status_code == 404
