import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from prometheus_client.parser import text_string_to_metric_families

from app.metrics import setup_metrics
from app.request_logging import log_request


@pytest.fixture
def metrics_client():
    app = FastAPI()
    app.middleware("http")(log_request)
    setup_metrics(app)

    @app.get("/items/{item_id}")
    def item(item_id: int):
        return {"id": item_id}

    @app.get("/denied")
    def denied():
        raise HTTPException(status_code=403, detail="Forbidden")

    @app.get("/broken")
    def broken():
        raise RuntimeError("private-error-message")

    with TestClient(app) as client:
        yield client


def read_samples(client):
    response = client.get("/metrics")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert "X-Request-ID" in response.headers

    return [
        sample
        for family in text_string_to_metric_families(response.text)
        for sample in family.samples
    ]


def sample_value(samples, name, labels):
    matches = [
        sample.value
        for sample in samples
        if sample.name == name and sample.labels == labels
    ]
    assert len(matches) == 1
    return matches[0]


@pytest.mark.parametrize(
    ("path", "status_code", "route"),
    [
        ("/items/7", 200, "/items/{item_id}"),
        ("/items/invalid", 422, "/items/{item_id}"),
        ("/denied", 403, "/denied"),
        ("/missing", 404, "<unmatched>"),
        ("/broken", 500, "/broken"),
    ],
)
def test_counts_response_status(
    metrics_client,
    path,
    status_code,
    route,
):
    response = metrics_client.get(path)
    assert response.status_code == status_code

    samples = read_samples(metrics_client)

    assert sample_value(
        samples,
        "ecommerce_http_requests_total",
        {
            "method": "GET",
            "route": route,
            "status_code": str(status_code),
        },
    ) == 1

    labels = {"method": "GET", "route": route}

    assert sample_value(
        samples,
        "ecommerce_http_response_ready_seconds_count",
        labels,
    ) == 1

    assert sample_value(
        samples,
        "ecommerce_http_response_ready_seconds_sum",
        labels,
    ) >= 0

    assert sample_value(
        samples,
        "ecommerce_http_response_ready_seconds_bucket",
        {**labels, "le": "+Inf"},
    ) == 1


def test_product_ids_share_one_metric_series(metrics_client):
    metrics_client.get("/items/100")
    metrics_client.get("/items/200")

    samples = read_samples(metrics_client)
    counters = [
        sample
        for sample in samples
        if sample.name == "ecommerce_http_requests_total"
    ]

    assert len(counters) == 1
    assert counters[0].labels == {
        "method": "GET",
        "route": "/items/{item_id}",
        "status_code": "200",
    }
    assert counters[0].value == 2


def test_unknown_paths_share_one_metric_series(metrics_client):
    metrics_client.get("/unknown-one")
    metrics_client.get("/unknown-two")

    samples = read_samples(metrics_client)

    assert sample_value(
        samples,
        "ecommerce_http_requests_total",
        {
            "method": "GET",
            "route": "<unmatched>",
            "status_code": "404",
        },
    ) == 2


def test_metrics_scrapes_do_not_change_metrics(metrics_client):
    metrics_client.get("/items/1")

    first = metrics_client.get("/metrics")
    second = metrics_client.get("/metrics")

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.content == second.content
    assert 'route="/metrics"' not in second.text


def test_metrics_exclude_request_secrets(metrics_client):
    response = metrics_client.get(
        "/items/123?token=private-query",
        headers={
            "Authorization": "Bearer private-token",
            "Cookie": "session=private-cookie",
            "X-Request-ID": "private-client-id",
        },
    )
    metrics_client.get("/broken")

    text = metrics_client.get("/metrics").text

    for value in [
        "private-query",
        "private-token",
        "private-cookie",
        "private-client-id",
        "private-error-message",
        response.headers["X-Request-ID"],
        "/items/123",
    ]:
        assert value not in text


def test_application_registries_are_independent():
    first_app = FastAPI()
    second_app = FastAPI()

    setup_metrics(first_app)
    setup_metrics(second_app)

    first_app.state.request_metrics.record(
        method="GET",
        route="/example",
        status_code=200,
        duration_seconds=0.1,
    )

    with TestClient(second_app) as client:
        samples = read_samples_without_logging(client)

    assert not any(
        sample.name == "ecommerce_http_requests_total"
        for sample in samples
    )


def read_samples_without_logging(client):
    response = client.get("/metrics")
    assert response.status_code == 200

    return [
        sample
        for family in text_string_to_metric_families(response.text)
        for sample in family.samples
    ]


def test_main_app_exposes_metrics(client):
    response = client.get("/health")
    assert response.status_code == 200

    samples = read_samples(client)

    assert sample_value(
        samples,
        "ecommerce_http_requests_total",
        {
            "method": "GET",
            "route": "/health",
            "status_code": "200",
        },
    ) >= 1