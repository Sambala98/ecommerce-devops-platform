import json
import logging
from uuid import UUID

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.request_logging import log_request, logger


@pytest.fixture
def logging_app(monkeypatch):
    entries = []

    def capture(level, message):
        entries.append((level, json.loads(message)))

    monkeypatch.setattr(logger, "log", capture)

    app = FastAPI()
    app.middleware("http")(log_request)

    @app.get("/items/{item_id}")
    def item(item_id: int):
        return {"id": item_id}

    @app.get("/denied")
    def denied():
        raise HTTPException(status_code=403, detail="Forbidden")

    @app.get("/broken")
    def broken():
        raise RuntimeError("private-exception-message")

    @app.post("/submit")
    def submit():
        return {"ok": True}

    with TestClient(app) as client:
        yield client, entries


@pytest.mark.parametrize(
    ("path", "status", "route"),
    [
        ("/items/7", 200, "/items/{item_id}"),
        ("/items/not-an-integer", 422, "/items/{item_id}"),
        ("/denied", 403, "/denied"),
        ("/missing", 404, "<unmatched>"),
    ],
)
def test_response_has_matching_request_log(
    logging_app,
    path,
    status,
    route,
):
    client, entries = logging_app
    response = client.get(path)

    assert response.status_code == status
    assert len(entries) == 1

    level, entry = entries[0]
    request_id = response.headers["X-Request-ID"]

    assert UUID(request_id).version == 4
    assert entry["request_id"] == request_id
    assert entry["method"] == "GET"
    assert entry["path"] == route
    assert entry["status_code"] == status
    assert entry["duration_ms"] >= 0
    assert level == logging.INFO


def test_unexpected_error_is_generic_and_logged(logging_app):
    client, entries = logging_app
    response = client.get("/broken")

    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error"}
    assert len(entries) == 1

    level, entry = entries[0]
    assert level == logging.ERROR
    assert entry["error_type"] == "RuntimeError"
    assert entry["status_code"] == 500
    assert entry["request_id"] == response.headers["X-Request-ID"]
    assert "private-exception-message" not in json.dumps(entry)


def test_request_secrets_are_excluded(logging_app):
    client, entries = logging_app
    response = client.post(
        "/submit?token=private-query",
        headers={
            "Authorization": "Bearer private-token",
            "Cookie": "session=private-cookie",
            "X-Request-ID": "untrusted-client-id",
        },
        json={"password": "private-password"},
    )

    assert response.status_code == 200
    assert len(entries) == 1

    logged = json.dumps(entries)
    for secret in [
        "private-query",
        "private-token",
        "private-cookie",
        "private-password",
        "untrusted-client-id",
    ]:
        assert secret not in logged

    assert response.headers["X-Request-ID"] != "untrusted-client-id"


def test_each_request_gets_a_unique_id(logging_app):
    client, entries = logging_app

    first = client.get("/items/1")
    second = client.get("/items/2")

    assert first.headers["X-Request-ID"] != second.headers["X-Request-ID"]
    assert len(entries) == 2


def test_main_app_registers_request_logging(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert UUID(response.headers["X-Request-ID"]).version == 4