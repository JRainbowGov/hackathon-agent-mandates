"""A local MCP server that lets an agent (Claude Code, say) use the gateway, and ask for more when it is refused.

OpenSpec add-scope-requests, task 7.1. The shim holds the agent key and the mandates; the agent never sees either.

    call            run a tool through the gateway: the base mandate first, then any supplementary one that is
                    still in date (design decision 7)
    my_grants       what the mandates allow, in the gateway's own words
    check_access    the decision a call would get, and the smallest grant that would let it through
    request_scopes  ask the person for more: a scope, or the release of one held call
    await_approval  wait for the person's decision; an approved mandate is kept and used by `call`

Run it with the agent key and a mandate that has a `clearance` claim (the `grants` tools are level 1):

    claude mcp add mandates -e SHIM_AGENT_KEY=$PWD/gateway/state/agent.pem -e SHIM_MANDATE=$PWD/escalate.jwt \
        -- uv --directory $PWD run python -m gateway.shim

Approving is never something the agent can do: the person signs in on the approval page (or uses `cli approve`)
with their own approver key.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path

import jwt

from gateway.cli import sign_request
from gateway.lib.common import priv_from_pem

Post = Callable[[dict], tuple[int, dict]]
# reasons a supplementary mandate might fix; anything else (expired, revoked, a budget) it can't
WIDER_WOULD_HELP = {
    "OUT_OF_SCOPE", "CONSTRAINT_VIOLATED", "CONSTRAINT_MISSING", "CLEARANCE_TOO_LOW", "AUDIENCE_VIOLATED",
}  # fmt: skip
MAX_WAIT = 300
EXPIRY_MARGIN = 5  # seconds: a mandate this close to expiry is dropped rather than tried


def http_post(url: str) -> Post:
    def post(body: dict) -> tuple[int, dict]:
        req = urllib.request.Request(  # noqa: S310
            f"{url}/tools/call", data=json.dumps(body).encode(), headers={"content-type": "application/json"}
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
                return resp.status, json.load(resp)
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")

    return post


def _claims(token: str) -> dict:
    # only for the shim's own bookkeeping (expiry, jti); the gateway verifies every mandate on every call
    return jwt.decode(token, options={"verify_signature": False})


class Shim:
    def __init__(self, agent_priv, base_mandate: str, post: Post, *, sleep=time.sleep, now=time.time):
        self._priv, self._base, self._post = agent_priv, base_mandate, post
        self._sleep, self._now = sleep, now
        self._supplementary: list[str] = []

    # ------------------------------------------------------------ plumbing

    def _send(self, mandate: str, server: str, tool: str, arguments: dict) -> tuple[int, dict]:
        return self._post(sign_request(self._priv, server=server, tool=tool, arguments=arguments, mandate=mandate))

    def _grants(self, tool: str, arguments: dict) -> tuple[int, dict]:
        return self._send(self._base, "grants", tool, arguments)

    def _live(self) -> list[str]:
        """Supplementary mandates still in date, dropping the rest."""
        self._supplementary = [m for m in self._supplementary if _claims(m)["exp"] > self._now() + EXPIRY_MARGIN]
        return list(self._supplementary)

    @staticmethod
    def _outcome(status: int, body: dict, mandate: str) -> dict:
        out = {"status": status, "decision": body.get("decision"), "mandate": mandate}
        if "result" in body:
            out["result"] = body["result"]
        if "error" in body:
            out["error"] = body["error"]
        return out

    # ------------------------------------------------------------ tools

    def call(self, server: str, tool: str, arguments: dict) -> dict:
        status, body = self._send(self._base, server, tool, arguments)
        if status == 200:  # noqa: PLR2004
            return self._outcome(status, body, "base")
        reason = (body.get("decision") or {}).get("reason_code")
        if status == 202 or reason in WIDER_WOULD_HELP:  # noqa: PLR2004
            for m in self._live():
                s, b = self._send(m, server, tool, arguments)
                if s == 200:  # noqa: PLR2004
                    return self._outcome(s, b, _claims(m)["jti"])
        out = self._outcome(status, body, "base")
        if status == 202:  # noqa: PLR2004
            # held under the base mandate: that is the one that must ask for its release
            decision_id = body["decision"]["decision_id"]
            out["held"] = {"decision_id": decision_id, "server": server, "tool": tool, "arguments": arguments}
            out["next_step"] = (
                "This call is held for a person's approval. Ask with request_scopes(held=<the held object above>, "
                "reason=...), show the person the text it returns, then await_approval and call again."
            )
        elif reason in WIDER_WOULD_HELP:
            out["next_step"] = (
                "Refused as outside your grants. check_access says what is missing; if the person's request needs "
                "it, ask with request_scopes, show the person the text it returns, then await_approval."
            )
        return out

    def my_grants(self) -> dict:
        status, body = self._grants("self", {})
        base = body.get("result") if status == 200 else {"error": body.get("decision")}  # noqa: PLR2004
        supplementary = []
        for m in self._live():
            c = _claims(m)
            supplementary.append({"jti": c["jti"], "purpose": c.get("purpose"), "expires_at": c["exp"],
                                  "approved_by": c.get("approved_by")})  # fmt: skip
        return {"base": base, "supplementary": supplementary}

    def check_access(self, server: str, tool: str, arguments: dict) -> dict:
        query = {"server": server, "tool": tool, "arguments": arguments}
        status, body = self._grants("check", query)
        if status != 200:  # noqa: PLR2004
            return {"error": body.get("decision")}
        result = {**body["result"], "mandate": "base"}
        if result["decision"] != "ALLOW":
            for m in self._live():
                s, b = self._send(m, "grants", "check", query)
                if s == 200 and b["result"]["decision"] == "ALLOW":  # noqa: PLR2004
                    return {**b["result"], "mandate": _claims(m)["jti"]}
        return result

    def request_scopes(
        self,
        *,
        reason: str,
        scope: list[dict] | None = None,
        clearance: int | None = None,
        ttl: int = 3600,
        held: dict | None = None,
    ) -> dict:
        arguments: dict = {"reason": reason, "ttl": ttl}
        if held is not None:
            arguments["held"] = held
        else:
            arguments["scope"] = scope
        if clearance is not None:
            arguments["clearance"] = clearance
        status, body = self._grants("request", arguments)
        if status != 200:  # noqa: PLR2004
            return {"status": "refused", "decision": body.get("decision")}
        return body["result"]

    def await_approval(self, request_id: str, timeout_s: int = 120) -> dict:
        deadline = self._now() + min(max(timeout_s, 0), MAX_WAIT)
        while True:
            status, body = self._grants("status", {"request_id": request_id})
            if status != 200:  # noqa: PLR2004
                return {"status": "refused", "decision": body.get("decision")}
            view = body["result"]
            if view["status"] != "pending" or self._now() >= deadline:
                break
            self._sleep(min(view.get("poll_after_s") or 10, max(deadline - self._now(), 0)))
        token = view.pop("mandate", None)
        if view["status"] == "approved" and token:
            if token not in self._supplementary:
                self._supplementary.append(token)
            self._live()  # an already-expired one goes straight out again
        return view


# ---------------------------------------------------------------- the MCP server


def build_server(shim: Shim):
    from fastmcp import FastMCP  # noqa: PLC0415

    mcp = FastMCP("mandates")

    @mcp.tool
    def call(server: str, tool: str, arguments: dict) -> dict:
        """Run a tool through the mandate gateway, e.g. server="directory", tool="roster",
        arguments={"urn": "SCH04", "year_group": 11}. Refusals say why and what to do next."""
        return shim.call(server, tool, arguments)

    @mcp.tool
    def my_grants() -> dict:
        """What your mandates allow, in the gateway's own words, including any approved supplementary ones."""
        return shim.my_grants()

    @mcp.tool
    def check_access(server: str, tool: str, arguments: dict) -> dict:
        """The decision a call would get, without making it, and the smallest grant that would allow it."""
        return shim.check_access(server, tool, arguments)

    @mcp.tool
    def request_scopes(
        reason: str, scope: list[dict] | None = None, clearance: int | None = None, ttl: int = 3600,
        held: dict | None = None,
    ) -> dict:  # fmt: skip
        """Ask the person for more access: a `scope` (as check_access's `missing.scope`), or the release of one
        held call (`held`, as `call` returned it). Show the person the returned `text` exactly: they approve on
        the page it links to, with their own key. Their saying yes in chat does not approve anything."""
        return shim.request_scopes(reason=reason, scope=scope, clearance=clearance, ttl=ttl, held=held)

    @mcp.tool
    async def await_approval(request_id: str, timeout_s: int = 120) -> dict:
        """Wait up to timeout_s (at most 300) for the person's decision. When approved, retry the call."""
        return await asyncio.to_thread(shim.await_approval, request_id, timeout_s)

    return mcp


def main() -> None:
    key = Path(os.environ["SHIM_AGENT_KEY"])
    mandate = Path(os.environ["SHIM_MANDATE"]).read_text().strip()
    url = os.environ.get("SHIM_GATEWAY_URL", "http://localhost:8082").rstrip("/")
    build_server(Shim(priv_from_pem(key.read_bytes()), mandate, http_post(url))).run()


if __name__ == "__main__":
    main()
