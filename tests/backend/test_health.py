def test_health_and_openapi_are_available(client) -> None:
    live = client.get("/health/live", headers={"X-Request-ID": "req-test-live"})
    ready = client.get("/health/ready")
    openapi = client.get("/openapi.json")

    assert live.status_code == 200
    assert live.json() == {"status": "ok"}
    assert live.headers["X-Request-ID"] == "req-test-live"
    assert ready.status_code == 200
    assert ready.json() == {"status": "ready"}
    assert openapi.status_code == 200
    assert "/api/v1/evaluation-jobs/{job_id}/report" in openapi.json()["paths"]
