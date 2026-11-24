# Deploying for Day 2

Only the gateway is public. Everything else stays on the Compose network or the host's loopback.

| Service | Reachable at | Why |
| --- | --- | --- |
| gateway | `:8082`, public | The one way in: `POST /tools/call` |
| backend (MCP), slices | Compose network only | Only the gateway calls them, with a signed tool grant |
| frontend (approval page) | `127.0.0.1:8081` | For your approvers, through an SSH tunnel |
| issuer | `127.0.0.1:8083` | The CLI's `approve`; the UI and gateway reach it over the network |

`docker-compose.deploy.yaml` makes these changes on top of the base file:
- it removes the backend's published port;
- it binds the UI to loopback;
- it forces the `/demo` routes off.

**Put TLS in front of the gateway.** `:8082` speaks plain HTTP. The request signature stops anyone changing a
call, but not reading it: the mandate, the arguments and the pupil data in the response all cross the network in
clear. On a shared network, terminate TLS in front of it (a reverse proxy, or the host's load balancer) and give
other teams the `https://` address. Use that address for `DEPLOY_URL` and `audit anchor` below.

## Where the issuer key lives

The issuer key (`gateway/state/issuer_key.pem`) signs every mandate and the revocation list. Anyone holding it can
grant anything, and a leaked key scores 50 points on Day 2. The gateway container no longer has it; only the issuer
service mounts it. Pick one setup:

| | Key on the server, in the issuer container | Key on a laptop only |
| --- | --- | --- |
| Approvals during Day 2 (scope requests, released held calls) | Work | Don't: the issuer can't mint |
| Revoking a team's mandate | `cli revoke` on the server | `cli revoke` on the laptop, then copy `status_list.jwt` and `status_list.json` to the server |
| Who can take the key | Anyone with a shell on the server | Nobody on the server |

- **Showing approvals live:** use the first setup and keep shell access to the server to the team.
- **Otherwise:** use the second. Run `make hack` on the laptop, then copy to the server only the public files the
  gateway mounts:
  - `trusted_list.json`, `status_list.json`, `status_list.jwt`;
  - `gateway_key.pem`, `gateway.pub`;
  - `tool_grant_key.pem`, `tool_grant.pub`.

  Leave out the `issuer` service: requests to `grants.request` then fail closed.

Either way, issue the attack mandates with `make attack_mandates` on the machine that holds the key, and post only
the `.jwt` files. Never post or copy `*.pem` beyond the list above.

## Steps

1. **On the server:** `make install`, and put the state files in place (above).
2. **Start:** `make deploy_up`.
3. **Check from outside the server:** `make deploy_check DEPLOY_URL=http://<host>:8082`. Wants:
   - 32/32, question 0 at 12/12;
   - demo routes `404`;
   - `{"store": "sqlite", "durable": true}`.

   Don't post the URL until all three hold.
4. **Mandates:** put each attacking team's `<team>.jwk` in `day_2_attack/keys/`, run `make attack_mandates` (with
   `FEATURE_SCOPE` and `FEATURE_CLAIMS` for the feature mandate), and post `day_2_attack/mandates/` with the
   enforcement note.
5. **During the attack window:**
   - from a laptop, not the server, save the audit chain head every minute:
     `while true; do uv run python -m gateway.cli audit anchor --url http://<host>:8082; sleep 60; done`
   - watch for `ALERT_PUPIL_TARGETED` and `ALERT_REFUSALS` with `cli audit events`, using a reader mandate for your
     principal ([audit-trail.md](audit-trail.md)).
6. **Afterwards:** check the chain against the saved heads, `cli audit verify --db <copy> --anchors audit_anchors.jsonl`.

## The approval page under a path prefix

The approval page can be served at `https://<host>/frontend`, next to the gateway at the root of the same CloudFront
distribution. The `Makefile` builds the UI under `/frontend` by default, and takes the public address from
`FRONTEND_URL`:

```make
PUBLIC_BASE_PATH ?= /frontend                              # the UI is built to answer under this
FRONTEND_URL ?= http://localhost:8081$(PUBLIC_BASE_PATH)   # the issuer builds approval_url from it
```

On a deployment, set `FRONTEND_URL` in `.env` (or the shell) before `make hack`:

```bash
cp -n .env.example .env   # first, or make hack won't fill in the rest of .env
echo 'FRONTEND_URL=https://<host>/frontend' >> .env
```

- `PUBLIC_BASE_PATH` is a build arg of the frontend image, fixed at build time. Pages, `/_astro/` assets, the approval
  API calls, the sign-in cookie's path and the redirect after sign-in all carry it (`frontend/src/lib/paths.ts`). The
  UI answers with or without the prefix, so the web server can strip it or pass it through.
- `FRONTEND_URL` goes to the issuer. Every `approval_url` an agent shows is built from it, so it must include the
  prefix.
- The `/demo` walkthrough doesn't follow the prefix. It's off on a deployed gateway anyway.

### Deploying it

1. **Infra: route `/frontend*` to the UI on port 8081.** Today the distribution's default behaviour goes to the
   gateway (`:8082`), and `/frontend/...` gets the gateway's `404`. Add a behaviour for `/frontend*` with:
   - the UI (`:8081`) as origin;
   - caching off (`CachingDisabled`): the approval view and the decision must never be cached;
   - every viewer header, cookie and query string forwarded (`AllViewer`): the sign-in token is a query string and
     the approver session a cookie;
   - `GET, HEAD, OPTIONS, PUT, POST, PATCH, DELETE` allowed: approving is a `POST`.
2. **On the server**, with `FRONTEND_URL` set in `.env` (above): `make hack`. It builds the UI with the prefix and
   starts the stack with `:8081` published. Not `make deploy_up`: that binds the UI to `127.0.0.1`, which CloudFront
   can't reach.
3. **Check the routing** from anywhere:

   ```bash
   curl -s -o /dev/null -w '%{http_code}\n' https://<host>/frontend/approve/sr_test123   # 200
   curl -s https://<host>/healthcheck                                    # the gateway
   ```

4. **Say who can approve, on the server.** The issuer only lets a person grant what they hold, from
   `gateway/state/principals.json`. `make hack` doesn't create it; without it every request is refused with
   `EXCEEDS_PRINCIPAL`. For example:

   ```json
   {"officer:jsmith": {"servers": {"directory": ["roster", "name"], "pupil-data": ["search", "pupil", "write"]},
    "urns": ["SCH01", "SCH02", "SCH03", "SCH04"], "max_clearance": 4}}
   ```

5. **Give each approver a key.** The issuer checks sign-in against `gateway/state/approvers.json` on the server. Make
   the key on the server, then move the private half to the approver's laptop and delete it from the server:

   ```bash
   uv run python -m gateway.cli approver-keygen --principal officer:jsmith -o jsmith-approver.pem   # on the server
   scp server:<repo>/jsmith-approver.pem .                                                          # on the laptop
   rm jsmith-approver.pem                                                                           # on the server
   ```

   Keep approver keys away from anywhere an agent runs: an agent that can read one can approve its own requests.
6. **Mandates for agents** come from the issuer key on the server, as for any mandate (`cli issue`). The grants tools
   need a `clearance` claim ([scope-requests.md](scope-requests.md)). Point the shim at the deployment with
   `SHIM_GATEWAY_URL=https://<host>`.
7. **Approve.** The agent shows an `approval_url` under `/frontend/approve/`. The approver signs in with a one-time
   link from their laptop, valid 5 minutes, then chooses the number the agent gave them:

   ```bash
   make approver_login PRINCIPAL=officer:jsmith KEY=jsmith-approver.pem REQUEST=sr_...
   ```

   The browser session lasts 30 minutes and covers every request for that person, so signing in before the agent
   starts works too. The agent picks the decision up within 3 seconds; nobody tells it.

### Know before Day 2

- **`ENVIRONMENT=local`**, which `make hack` copies into `.env`, turns off the UI's check for the ALB's OIDC header
  (`x-amzn-oidc-data`). The approval page is then public, guarded only by approver sign-in. Any other value needs
  ALB OIDC authentication on the route, or every page sends you to `/unauthorised`; CloudFront alone can't add the
  header.
- The issuer is reached at `127.0.0.1:8083` on the server only. `cli approve` from a laptop doesn't reach it; approve
  on the page.
- Login tokens, sessions and pending requests live in the issuer's SQLite volume. `make stop` keeps it; a fresh
  server signs everyone out and drops pending requests.

## Changed for Day 2 (this change)

- **No grace on `exp`.** A mandate is refused from the second it expires. The 30 seconds of clock skew stay on `nbf`
  only, where they forgive a freshly issued mandate. An expired mandate accepted for 30 seconds would have scored as a
  "Dead mandate".
- **`/demo` is off unless `GATEWAY_ENABLE_DEMO=1`.** It answers `404`. The walkthrough at `:8081/demo` no longer works
  even with the variable set: it mints and revokes with the issuer key, which stays with the issuer service. Use the
  CLI (`cli issue`, `cli call`, `cli revoke`) instead.
