"""OpenTelemetry tracing for the gateway: FastAPI server spans, fastmcp/MCP client spans and outbound httpx spans.

(The MCP client itself uses httpx2, which the httpx instrumentor does not hook; its own "MCP send ..." spans
cover that hop.)

Off unless OTEL_EXPORTER_OTLP_ENDPOINT is set (docker-compose.observability.yaml sets it). With it unset,
nothing is imported from the OTel SDK and the gateway behaves exactly as before.

Traces must never carry pupil data. Tool arguments and results are where PII lands, so:
- the gateway only ever adds the attributes in `annotate_decision`: server, tool, decision, reason_code,
  policy version, argument *keys* and a hash of the mandate jti. Never argument values, results or
  Decision.detail (which can quote an argument value, e.g. CONSTRAINT_VIOLATED "urn='SCH02'");
- every exported span goes through `RedactingExporter`, which keeps only allowlisted attribute keys,
  drops event attributes except exception.type, and blanks status descriptions. That covers spans other
  libraries create too (fastmcp copies tool-error text into the span status; exception events carry
  messages). A new attribute stays invisible until someone adds it to ALLOWED_ATTRIBUTES on purpose.
"""

from __future__ import annotations

import hashlib
import logging
import os
from collections.abc import Sequence
from typing import TYPE_CHECKING

import jwt
from opentelemetry import trace

if TYPE_CHECKING:
    from fastapi import FastAPI
    from opentelemetry.sdk.trace import ReadableSpan
    from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult

log = logging.getLogger(__name__)

ENDPOINT_ENV = "OTEL_EXPORTER_OTLP_ENDPOINT"
DEFAULT_SERVICE_NAME = "mandate-gateway"

# Attributes the gateway itself sets on the /tools/call server span.
GATEWAY_ATTRIBUTES = frozenset({
    "gateway.server",
    "gateway.tool",
    "gateway.decision",
    "gateway.reason_code",
    "gateway.policy_version",
    "gateway.arg_keys",
    "gateway.jti_hash",
})

# Attributes from FastAPI/ASGI, httpx and fastmcp spans that carry no request content. Deliberately absent:
# http.target, http.url, url.full, url.query (query strings), any header or body capture.
ALLOWED_ATTRIBUTES = GATEWAY_ATTRIBUTES | frozenset({
    "http.method",
    "http.request.method",
    "http.status_code",
    "http.response.status_code",
    "http.route",
    "http.scheme",
    "http.flavor",
    "url.path",
    "url.scheme",
    "server.address",
    "server.port",
    "client.address",
    "net.peer.name",
    "net.peer.port",
    "net.host.name",
    "net.host.port",
    "network.protocol.version",
    "user_agent.original",
    "error.type",
    "rpc.system",
    "rpc.method",
    "rpc.response.status_code",
    "mcp.method.name",
    "mcp.session.id",
    "mcp.protocol.version",
    "gen_ai.tool.name",
    "gen_ai.operation.name",
    "fastmcp.component.key",
})
ALLOWED_EVENT_ATTRIBUTES = frozenset({"exception.type"})

_configured = False


def jti_hash(mandate: str) -> str | None:
    """sha256 of the mandate's jti, read without verifying (it is only a correlation key, never trusted)."""
    try:
        jti = jwt.decode(mandate, options={"verify_signature": False}).get("jti")
    except jwt.PyJWTError:
        return None
    if not isinstance(jti, str):
        return None
    return "sha256:" + hashlib.sha256(jti.encode()).hexdigest()


def decision_attributes(server: str, tool: str, arguments: dict, mandate: str, record: dict) -> dict:
    """The only gateway facts that go into a trace. Takes argument keys, never values."""
    attrs = {
        "gateway.server": server,
        "gateway.tool": tool,
        "gateway.decision": str(record.get("decision", "")),
        "gateway.reason_code": str(record.get("reason_code", "")),
        "gateway.policy_version": str(record.get("policy_version", "")),
        "gateway.arg_keys": sorted(str(k) for k in arguments),
    }
    h = jti_hash(mandate)
    if h:
        attrs["gateway.jti_hash"] = h
    return attrs


def annotate_decision(server: str, tool: str, arguments: dict, mandate: str, record: dict) -> None:
    """Tag the current request span with the decision. A no-op when tracing is off."""
    span = trace.get_current_span()
    if span.is_recording():
        span.set_attributes(decision_attributes(server, tool, arguments, mandate, record))


def redact_span(span: ReadableSpan) -> ReadableSpan:
    """A copy of the span with only allowlisted attributes, scrubbed events and no status description."""
    from opentelemetry.sdk.trace import Event, ReadableSpan  # noqa: PLC0415
    from opentelemetry.trace import Link, Status  # noqa: PLC0415

    def keep(attrs, allowed) -> dict:
        return {k: v for k, v in (attrs or {}).items() if k in allowed}

    return ReadableSpan(
        name=span.name,
        context=span.context,
        parent=span.parent,
        resource=span.resource,
        attributes=keep(span.attributes, ALLOWED_ATTRIBUTES),
        events=[Event(e.name, keep(e.attributes, ALLOWED_EVENT_ATTRIBUTES), e.timestamp) for e in span.events],
        links=[Link(link.context) for link in span.links],
        kind=span.kind,
        status=Status(span.status.status_code),
        start_time=span.start_time,
        end_time=span.end_time,
        instrumentation_scope=span.instrumentation_scope,
    )


def redacting_exporter(inner: SpanExporter) -> SpanExporter:
    """Wrap an exporter so every span is redacted before it leaves the process."""
    from opentelemetry.sdk.trace.export import SpanExporter  # noqa: PLC0415

    class RedactingExporter(SpanExporter):
        def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
            return inner.export([redact_span(s) for s in spans])

        def shutdown(self) -> None:
            inner.shutdown()

        def force_flush(self, timeout_millis: int = 30000) -> bool:
            return inner.force_flush(timeout_millis)

    return RedactingExporter()


def setup(app: FastAPI) -> bool:
    """Install tracing if OTEL_EXPORTER_OTLP_ENDPOINT is set. Returns whether tracing is on."""
    global _configured  # noqa: PLW0603
    if not os.environ.get(ENDPOINT_ENV) or _configured:
        return _configured

    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter  # noqa: PLC0415
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor  # noqa: PLC0415
    from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor  # noqa: PLC0415
    from opentelemetry.sdk.resources import Resource  # noqa: PLC0415
    from opentelemetry.sdk.trace import TracerProvider  # noqa: PLC0415
    from opentelemetry.sdk.trace.export import BatchSpanProcessor  # noqa: PLC0415

    service = os.environ.get("OTEL_SERVICE_NAME", DEFAULT_SERVICE_NAME)
    provider = TracerProvider(resource=Resource.create({"service.name": service}))
    # OTLPSpanExporter reads OTEL_EXPORTER_OTLP_ENDPOINT and appends /v1/traces
    provider.add_span_processor(BatchSpanProcessor(redacting_exporter(OTLPSpanExporter())))
    trace.set_tracer_provider(provider)  # fastmcp's own client spans use the global provider

    FastAPIInstrumentor.instrument_app(
        app,
        tracer_provider=provider,
        excluded_urls="healthcheck",  # the 3s container probe would bury real traces
        exclude_spans=["receive", "send"],
    )
    HTTPXClientInstrumentor().instrument(tracer_provider=provider)
    _configured = True
    log.info("tracing on: OTLP to %s as %s", os.environ[ENDPOINT_ENV], service)
    return True
