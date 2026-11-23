"""Traces never carry pupil data: argument values, results and Decision.detail stay out of exported spans."""

import asyncio
import json

import jwt
import pytest

from gateway import cli, main
from gateway import eval as ev
from gateway.lib import db, telemetry
from gateway.lib.common import priv_from_pem
from gateway.tests.test_gateway import gw  # noqa: F401  (fixture)

sdk_trace = pytest.importorskip("opentelemetry.sdk.trace")
from opentelemetry.sdk.trace.export import SimpleSpanProcessor  # noqa: E402
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter  # noqa: E402
from opentelemetry.trace import Status, StatusCode  # noqa: E402


@pytest.fixture
def traced():
    memory = InMemorySpanExporter()
    provider = sdk_trace.TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(telemetry.redacting_exporter(memory)))
    yield provider.get_tracer("test"), memory
    provider.shutdown()


def dump(spans) -> str:
    return json.dumps(
        [
            {
                "name": s.name,
                "attributes": dict(s.attributes),
                "events": [{"name": e.name, "attributes": dict(e.attributes)} for e in s.events],
                "status": s.status.description,
            }
            for s in spans
        ],
        default=str,
    )


def test_redactor_keeps_only_allowlisted_attributes(traced):
    tracer, memory = traced
    with tracer.start_as_current_span("tools/call search") as span:
        span.set_attributes(
            {
                "gen_ai.tool.name": "search",
                "http.target": "/tools/call?pupil=P0004",
                "mcp.tool.arguments": '{"query": "P0004"}',
                "gateway.result": "Ada Lovelace",
            }
        )
        span.add_event("exception", {"exception.type": "ToolError", "exception.message": "no pupil P0004"})
        span.set_status(Status(StatusCode.ERROR, "pupil P0004 not found"))

    (out,) = memory.get_finished_spans()
    assert dict(out.attributes) == {"gen_ai.tool.name": "search"}
    assert dict(out.events[0].attributes) == {"exception.type": "ToolError"}
    assert out.status.status_code == StatusCode.ERROR
    assert out.status.description is None
    assert "P0004" not in dump([out])
    assert "Ada" not in dump([out])


def test_gateway_span_has_keys_not_values(gw, traced):  # noqa: F811
    _client, _call, state = gw
    tracer, memory = traced
    agent_priv = priv_from_pem((state / "agent.pem").read_bytes())
    mandate = (state / "mandate.jwt").read_text()

    def tools_call(span_name, **arguments):
        signed = cli.sign_request(agent_priv, server="pupil-data", tool="search", arguments=arguments, mandate=mandate)
        with tracer.start_as_current_span(span_name):
            return asyncio.run(main.tools_call(main.CallBody(**signed)))

    allowed = tools_call("allow", query=ev.PUPIL, urn="SCH01")
    assert allowed["decision"]["decision"] == "ALLOW"
    denied = tools_call("deny", query="P0999", urn="SCH07")
    assert denied.status_code == 403
    assert json.loads(denied.body)["decision"]["reason_code"] == "CONSTRAINT_VIOLATED"

    spans = {s.name: s for s in memory.get_finished_spans()}
    allow, deny = dict(spans["allow"].attributes), dict(spans["deny"].attributes)
    assert allow["gateway.decision"] == "ALLOW"
    assert allow["gateway.reason_code"] == "IN_SCOPE"
    assert tuple(allow["gateway.arg_keys"]) == ("query", "urn")
    assert allow["gateway.jti_hash"].startswith("sha256:")
    assert deny["gateway.reason_code"] == "CONSTRAINT_VIOLATED"

    exported = dump(spans.values())
    for value in (ev.PUPIL, "SCH01", "P0999", "SCH07"):
        assert value not in exported, value
    # the jti itself is not exported, only its hash
    jti = jwt.decode(mandate, options={"verify_signature": False})["jti"]
    assert jti not in exported


def test_off_without_env(monkeypatch):
    monkeypatch.delenv(telemetry.ENDPOINT_ENV, raising=False)
    monkeypatch.delenv(db.URL_ENV, raising=False)
    assert telemetry.setup(main.app) is False
    assert asyncio.run(db.health()) == {"status": "disabled"}


def test_db_healthcheck_route_disabled(gw):  # noqa: F811
    client, _call, _state = gw
    r = client.get("/healthcheck/db")
    assert r.status_code == 200
    assert r.json() == {"status": "disabled"}
