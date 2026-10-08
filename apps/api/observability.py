"""Request tracing, structured logs, and small in-process metrics for ATLAS."""
import json
import logging
import os
import re
import sys
import threading
from collections import Counter
from time import monotonic, perf_counter
from uuid import uuid4

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.propagate import extract
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import SpanKind, Status, StatusCode


REQUEST_ID = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


class JsonFormatter(logging.Formatter):
    def format(self, record):
        payload = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname.lower(),
            "logger": record.name,
            "message": record.getMessage(),
        }
        for field in (
            "request_id",
            "trace_id",
            "method",
            "route",
            "status_code",
            "duration_ms",
        ):
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, separators=(",", ":"))


def request_logger():
    logger = logging.getLogger("atlas.api.requests")
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    return logger


def tracer_provider(endpoint=None):
    provider = TracerProvider(
        resource=Resource.create({"service.name": "atlas-api"})
    )
    endpoint = endpoint or os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    if endpoint:
        provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint.rstrip("/") + "/v1/traces"))
        )
    return provider


class Metrics:
    def __init__(self):
        self.started_at = monotonic()
        self.in_progress = 0
        self.requests = Counter()
        self.duration = Counter()
        self._lock = threading.Lock()

    def begin(self):
        with self._lock:
            self.in_progress += 1

    def finish(self, method, route, status, duration):
        key = (method, route, str(status))
        with self._lock:
            self.in_progress -= 1
            self.requests[key] += 1
            self.duration[key] += duration

    def render(self, robots, missions, incidents):
        with self._lock:
            requests = self.requests.copy()
            durations = self.duration.copy()
            in_progress = self.in_progress
        lines = [
            "# HELP atlas_process_uptime_seconds Seconds since this API process started.",
            "# TYPE atlas_process_uptime_seconds gauge",
            f"atlas_process_uptime_seconds {monotonic() - self.started_at:.6f}",
            "# HELP atlas_http_requests_in_progress Requests currently being handled.",
            "# TYPE atlas_http_requests_in_progress gauge",
            f"atlas_http_requests_in_progress {in_progress}",
            "# HELP atlas_http_requests_total Completed HTTP requests.",
            "# TYPE atlas_http_requests_total counter",
        ]
        for key in sorted(requests):
            method, route, status = key
            labels = f'method="{method}",route="{_escape(route)}",status="{status}"'
            lines.append(f"atlas_http_requests_total{{{labels}}} {requests[key]}")
        lines.extend([
            "# HELP atlas_http_request_duration_seconds Total request duration.",
            "# TYPE atlas_http_request_duration_seconds counter",
        ])
        for key in sorted(durations):
            method, route, status = key
            labels = f'method="{method}",route="{_escape(route)}",status="{status}"'
            lines.append(
                f"atlas_http_request_duration_seconds{{{labels}}} {durations[key]:.6f}"
            )
        _append_gauges(lines, "atlas_robots", "Robots by current status.", robots)
        _append_gauges(lines, "atlas_missions", "Missions by current status.", missions)
        _append_gauges(lines, "atlas_incidents", "Incidents by current status.", incidents)
        return "\n".join(lines) + "\n"


def _escape(value):
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _append_gauges(lines, name, help_text, values):
    lines.extend([f"# HELP {name} {help_text}", f"# TYPE {name} gauge"])
    for status, count in sorted(values.items()):
        lines.append(f'{name}{{status="{_escape(status)}"}} {count}')


def install_observability(app, provider, metrics, logger=None):
    tracer = provider.get_tracer("atlas.api")
    logger = logger or request_logger()

    @app.middleware("http")
    async def observe_request(request, call_next):
        supplied_id = request.headers.get("X-Request-ID", "")
        request_id = supplied_id if REQUEST_ID.fullmatch(supplied_id) else str(uuid4())
        method = request.method
        path = request.url.path
        status_code = 500
        started = perf_counter()
        metrics.begin()
        with tracer.start_as_current_span(
            f"{method} {path}",
            context=extract(request.headers),
            kind=SpanKind.SERVER,
            attributes={"http.request.method": method, "url.path": path},
        ) as span:
            try:
                response = await call_next(request)
                status_code = response.status_code
                response.headers["X-Request-ID"] = request_id
                return response
            except Exception as error:
                span.record_exception(error)
                span.set_status(Status(StatusCode.ERROR))
                raise
            finally:
                route = getattr(request.scope.get("route"), "path", "unmatched")
                duration = perf_counter() - started
                metrics.finish(method, route, status_code, duration)
                span.update_name(f"{method} {route}")
                span.set_attribute("http.route", route)
                span.set_attribute("http.response.status_code", status_code)
                span.set_attribute("atlas.request_id", request_id)
                trace_id = f"{span.get_span_context().trace_id:032x}"
                logger.info(
                    "request.completed",
                    extra={
                        "request_id": request_id,
                        "trace_id": trace_id,
                        "method": method,
                        "route": route,
                        "status_code": status_code,
                        "duration_ms": round(duration * 1000, 3),
                    },
                )
