import json
import logging
import sys
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from time import perf_counter
from uuid import uuid4

from fastapi import Request, Response
from fastapi.responses import JSONResponse


logger = logging.getLogger("ecommerce.requests")


def configure_request_logging() -> None:
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)

    logger.setLevel(logging.INFO)
    logger.propagate = False


async def log_request(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    request_id = str(uuid4())
    request.state.request_id = request_id
    started = perf_counter()
    error_type = None

    try:
        response = await call_next(request)
    except Exception as error:
        error_type = type(error).__name__
        response = JSONResponse(
            status_code=500,
            content={"detail": "Internal server error"},
        )

    duration_seconds = perf_counter() - started
    response.headers["X-Request-ID"] = request_id

    route = request.scope.get("route")
    route_path = getattr(route, "path", "<unmatched>")

    metrics = getattr(
        request.app.state,
        "request_metrics",
        None,
    )
    if metrics is not None:
        metrics.record(
            method=request.method,
            route=route_path,
            status_code=response.status_code,
            duration_seconds=duration_seconds,
        )

    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event": "http_response_ready",
        "request_id": request_id,
        "method": request.method,
        "path": route_path,
        "status_code": response.status_code,
        "duration_ms": round(duration_seconds * 1000, 3),
    }

    if error_type is not None:
        entry["error_type"] = error_type

    level = (
        logging.ERROR
        if response.status_code >= 500
        else logging.INFO
    )
    logger.log(level, json.dumps(entry))

    return response