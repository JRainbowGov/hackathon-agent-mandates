"""The issuer's own records (OpenSpec add-scope-requests, design decision 4): scope requests, approver logins and
sessions, seen nonces, and the outbox of signed audit events still to deliver to the gateway. SQLite, one file.
"""

from __future__ import annotations

import json
import secrets
import sqlite3
import threading
import time
import uuid
from pathlib import Path

USER_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTVWXYZ23456789"  # no 0/O, 1/I/L, U/V look-alikes
REQUEST_TTL = 15 * 60
MAX_PENDING = 3
MAX_PER_HOUR = 10

SCHEMA = """
CREATE TABLE IF NOT EXISTS requests (
    id TEXT PRIMARY KEY,
    requester_jti TEXT NOT NULL,
    requester_agent_id TEXT,
    principal TEXT NOT NULL,
    org TEXT,
    cnf_jwk TEXT NOT NULL,
    parent_mandate_hash TEXT NOT NULL,
    parent_status TEXT NOT NULL,
    parent_exp INTEGER NOT NULL,
    parent_clearance INTEGER,
    deny TEXT NOT NULL,
    requested TEXT NOT NULL,
    request_key TEXT NOT NULL,
    held TEXT,
    reason TEXT NOT NULL,
    user_code TEXT NOT NULL,
    ref_decision_id TEXT,
    created INTEGER NOT NULL,
    expires INTEGER NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('pending', 'approved', 'rejected', 'expired')),
    decided_by TEXT,
    decided_at INTEGER,
    approved TEXT,
    minted_jti TEXT,
    minted TEXT
);
CREATE INDEX IF NOT EXISTS requests_by_requester ON requests (requester_jti, created);
CREATE TABLE IF NOT EXISTS refused_decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT, request_id TEXT, reason TEXT NOT NULL, ts INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS login_tokens (jti TEXT PRIMARY KEY, used_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, principal TEXT NOT NULL, expires INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS nonces (nonce TEXT PRIMARY KEY, ts INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS outbox (
    id INTEGER PRIMARY KEY AUTOINCREMENT, event TEXT NOT NULL, created INTEGER NOT NULL, sent INTEGER
);
"""

JSON_FIELDS = ("cnf_jwk", "parent_status", "deny", "requested", "held", "decided_by", "approved")


class AlreadyDecided(Exception):
    pass


def user_code() -> str:
    raw = "".join(secrets.choice(USER_CODE_ALPHABET) for _ in range(8))
    return f"{raw[:4]}-{raw[4:]}"


class Store:
    def __init__(self, path: Path | str):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(self.path, check_same_thread=False, isolation_level=None)
        self._db.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        self._db.executescript(SCHEMA)

    # ------------------------------------------------------------ helpers

    def _row(self, row: sqlite3.Row | None) -> dict | None:
        if row is None:
            return None
        d = dict(row)
        for k in JSON_FIELDS:
            if d.get(k) is not None:
                d[k] = json.loads(d[k])
        return d

    def _exec(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        with self._lock:
            return self._db.execute(sql, params)

    # ------------------------------------------------------------ nonces

    def use_nonce(self, nonce: str, now: int | None = None) -> bool:
        """True the first time a nonce is seen; nonces older than 10 minutes are forgotten."""
        now = now or int(time.time())
        self._exec("DELETE FROM nonces WHERE ts < ?", (now - 600,))
        try:
            self._exec("INSERT INTO nonces (nonce, ts) VALUES (?, ?)", (nonce, now))
        except sqlite3.IntegrityError:
            return False
        return True

    # ------------------------------------------------------------ requests

    def counts(self, requester_jti: str, request_key: str, now: int | None = None) -> dict:
        now = now or int(time.time())
        self.expire_due(now)
        q = "SELECT COUNT(*) FROM requests WHERE requester_jti = ?"
        pending = self._exec(q + " AND status = 'pending'", (requester_jti,)).fetchone()[0]
        last_hour = self._exec(q + " AND created >= ?", (requester_jti, now - 3600)).fetchone()[0]
        rejected = self._exec(
            q + " AND status = 'rejected' AND request_key = ? AND decided_at >= ?",
            (requester_jti, request_key, now - 3600),
        ).fetchone()[0]
        return {"pending": pending, "last_hour": last_hour, "recently_rejected": rejected}

    def create(self, **fields) -> dict:
        now = int(time.time())
        rid = "sr_" + secrets.token_urlsafe(9)
        row = {
            "id": rid,
            "user_code": user_code(),
            "created": now,
            "expires": now + REQUEST_TTL,
            "status": "pending",
            **fields,
        }
        cols = list(row)
        values = [json.dumps(row[c]) if c in JSON_FIELDS and row[c] is not None else row[c] for c in cols]
        self._exec(
            f"INSERT INTO requests ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",  # noqa: S608
            tuple(values),
        )
        return self.get(rid)

    def get(self, rid: str) -> dict | None:
        self.expire_due()
        return self._row(self._exec("SELECT * FROM requests WHERE id = ?", (rid,)).fetchone())

    def pending_for(self, requester_jti: str) -> list[dict]:
        self.expire_due()
        rows = self._exec(
            "SELECT * FROM requests WHERE requester_jti = ? AND status = 'pending' ORDER BY created", (requester_jti,)
        ).fetchall()
        return [self._row(r) for r in rows]

    def approved_for(self, requester_jti: str) -> list[dict]:
        """Approved requests from one base mandate that minted a mandate and released no held call, newest first.

        These are the run's earlier approvals, which a later request may reuse (add-run-reuse).
        """
        rows = self._exec(
            "SELECT * FROM requests WHERE requester_jti = ? AND status = 'approved' AND held IS NULL "
            "AND minted IS NOT NULL ORDER BY decided_at DESC, created DESC",
            (requester_jti,),
        ).fetchall()
        return [self._row(r) for r in rows]

    def expire_due(self, now: int | None = None) -> list[dict]:
        """Mark pending requests past their expiry as expired; returns them so their events can be sent."""
        now = now or int(time.time())
        with self._lock:
            rows = self._db.execute(
                "SELECT * FROM requests WHERE status = 'pending' AND expires <= ?", (now,)
            ).fetchall()
            self._db.execute(
                "UPDATE requests SET status = 'expired', decided_at = ? WHERE status = 'pending' AND expires <= ?",
                (now, now),
            )
        expired = [self._row(r) for r in rows]
        for r in expired:
            self.enqueue({"event_type": "approval_expired", "request": r, "reason_code": "EXPIRED"})
        return expired

    def decide(self, rid: str, status: str, decided_by: dict, approved: dict | None = None) -> dict:
        """The one decision a request gets. Raises AlreadyDecided if it is no longer pending."""
        now = int(time.time())
        self.expire_due(now)
        cur = self._exec(
            "UPDATE requests SET status = ?, decided_by = ?, decided_at = ?, approved = ? "
            "WHERE id = ? AND status = 'pending'",
            (status, json.dumps(decided_by), now, json.dumps(approved) if approved else None, rid),
        )
        if cur.rowcount != 1:
            raise AlreadyDecided(rid)
        return self.get(rid)

    def set_minted(self, rid: str, jti: str, token: str) -> None:
        self._exec("UPDATE requests SET minted_jti = ?, minted = ? WHERE id = ?", (jti, token, rid))

    def refuse(self, rid: str | None, reason: str) -> None:
        self._exec(
            "INSERT INTO refused_decisions (request_id, reason, ts) VALUES (?, ?, ?)", (rid, reason, int(time.time()))
        )

    def refused(self, rid: str) -> list[dict]:
        rows = self._exec("SELECT * FROM refused_decisions WHERE request_id = ? ORDER BY id", (rid,)).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------ approvers

    def use_login_token(self, jti: str) -> bool:
        try:
            self._exec("INSERT INTO login_tokens (jti, used_at) VALUES (?, ?)", (jti, int(time.time())))
        except sqlite3.IntegrityError:
            return False
        return True

    def new_session(self, principal: str, ttl: int = 30 * 60) -> dict:
        sid = secrets.token_urlsafe(32)
        expires = int(time.time()) + ttl
        self._exec("INSERT INTO sessions (id, principal, expires) VALUES (?, ?, ?)", (sid, principal, expires))
        return {"session": sid, "principal": principal, "expires": expires}

    def session_principal(self, sid: str | None) -> str | None:
        if not sid:
            return None
        row = self._exec("SELECT principal, expires FROM sessions WHERE id = ?", (sid,)).fetchone()
        if row is None or row["expires"] < time.time():
            return None
        return row["principal"]

    # ------------------------------------------------------------ outbox

    def enqueue(self, event: dict) -> None:
        self._exec(
            "INSERT INTO outbox (event, created) VALUES (?, ?)",
            (json.dumps({"id": str(uuid.uuid4()), **event}, default=str), int(time.time())),
        )

    def unsent(self, limit: int = 50) -> list[tuple[int, dict]]:
        rows = self._exec("SELECT id, event FROM outbox WHERE sent IS NULL ORDER BY id LIMIT ?", (limit,)).fetchall()
        return [(r["id"], json.loads(r["event"])) for r in rows]

    def mark_sent(self, outbox_id: int) -> None:
        self._exec("UPDATE outbox SET sent = ? WHERE id = ?", (int(time.time()), outbox_id))
