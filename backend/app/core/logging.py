import json
import logging
from datetime import datetime, timezone


class JsonFormatter(logging.Formatter):
    def format(self, record):
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "severity_text": record.levelname,
            "body": record.getMessage(),
            "service.name": "agent-platform",
        }
        for key in (
            "job_id",
            "error_type",
            "request_id",
            "trace_id",
            "span_id",
            "step",
            "duration_ms",
        ):
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        from opentelemetry import trace

        span = trace.get_current_span().get_span_context()
        if span.is_valid:
            payload.update(
                trace_id=format(span.trace_id, "032x"),
                span_id=format(span.span_id, "016x"),
            )
        return json.dumps(payload)


def configure_logging():
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logging.getLogger().handlers = [handler]
    logging.getLogger().setLevel(logging.INFO)
    # Never log provider HTTP headers or bodies.
    logging.getLogger("httpx").setLevel(logging.WARNING)
