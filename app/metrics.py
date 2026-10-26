from fastapi import FastAPI, Response
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Histogram,
    generate_latest,
)


KNOWN_METHODS = frozenset({
    "GET",
    "POST",
    "PUT",
    "PATCH",
    "DELETE",
    "HEAD",
    "OPTIONS",
    "TRACE",
    "CONNECT",
})


class RequestMetrics:
    def __init__(self) -> None:
        self.registry = CollectorRegistry()

        self.requests = Counter(
            "ecommerce_http_requests_total",
            "HTTP responses ready, excluding the metrics endpoint.",
            ["method", "route", "status_code"],
            registry=self.registry,
        )

        self.duration = Histogram(
            "ecommerce_http_response_ready_seconds",
            "Time until HTTP response is ready, in seconds.",
            ["method", "route"],
            registry=self.registry,
            buckets=(
                0.005,
                0.01,
                0.025,
                0.05,
                0.1,
                0.25,
                0.5,
                1,
                2.5,
                5,
                10,
            ),
        )

    def record(
        self,
        method: str,
        route: str,
        status_code: int,
        duration_seconds: float,
    ) -> None:
        if route == "/metrics":
            return

        method_label = (
            method if method in KNOWN_METHODS else "OTHER"
        )

        self.requests.labels(
            method=method_label,
            route=route,
            status_code=str(status_code),
        ).inc()

        self.duration.labels(
            method=method_label,
            route=route,
        ).observe(duration_seconds)

    def response(self) -> Response:
        return Response(
            content=generate_latest(self.registry),
            headers={"Content-Type": CONTENT_TYPE_LATEST},
        )


def setup_metrics(app: FastAPI) -> None:
    metrics = RequestMetrics()
    app.state.request_metrics = metrics

    @app.get("/metrics", include_in_schema=False)
    def metrics_endpoint() -> Response:
        return metrics.response()