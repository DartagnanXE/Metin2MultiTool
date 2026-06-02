# Metin2FishBot Ranking API (server/)

**Artifacts + plan ONLY.** Nothing here connects to or modifies any live server.
This directory is the design, code, and config for the optional online ranking
backend; the actual deployment is a separate manual step you run yourself.

## What it is

A tiny, hardened HTTP API that backs the in-app **anonymous** ranking. The wire
field `hwid` carries a **random per-install id** (NOT a device hash); the chosen
name is **optional** (without one a row shows a deterministic anonymous name).

- `POST /submit` — a client sends its stats (random install id as `hwid`,
  catches, solved puzzles, runtimes, app version, timestamp, and an **optional**
  chosen name). Validated **strictly** (schema, types, length caps, sane numeric
  maxima; the name may be blank), rate-limited per-IP and per-install, and
  checked for implausible jumps. The raw IP is never stored — only a salted hash
  (GDPR).
- `GET /leaderboard?period=daily|all` — the aggregated board (MAX counters per
  install, blocked installs excluded, hidden names blanked), short in-process
  cache. Each row's display name = the chosen name if set + not hidden, else the
  anonymous funny name computed server-side from the install id.
- `POST /admin/{ban,unban,delete}` + `GET /admin/bans` — **block/unblock an
  install id** (`kind=install`), **hide/unhide a chosen name** (`kind=name`), and
  delete entries (GDPR erasure, by id or name). Neither is a durable person-ban.
  Auth is a strong env-var token (`ADMIN_TOKEN`), compared in constant time,
  **never embedded in the client**. A CLI (`server/cli.py`) calls the same
  functions inside the container.

## Stack & why

FastAPI + uvicorn + pydantic, in its **own** container:

- The whole repo is Python and is reviewed by Python eyes — one language.
- pydantic gives strict schema validation for almost no code.
- Small dependency surface (`server/requirements.txt`), pinned.

A Go binary was considered; the honor-system leaderboard does not justify a
second language/toolchain in this repo.

## How it maps to the client

| Client (`telemetry/`)              | Server                                      |
| ---------------------------------- | ------------------------------------------- |
| `payload.build_submit(...)` schema | `app/schemas.py:SubmitIn` (name optional)   |
| random install id (`hwid` field)   | `submissions.hwid` (random id, not a hash)  |
| `anon_name.anon_name(id)` (local)  | `app/anon_name.py` (canonical EN, verbatim) |
| `client.post_submit(url, payload)` | `POST /submit` (`app/routes_submit.py`)     |
| `client.fetch_leaderboard(url)`    | `GET /leaderboard` (`routes_leaderboard`)   |
| `'banned'` response → stop sending | blocked install → `{status:'banned'}`       |

## Isolation (hard constraint)

The target box co-hosts a valuable `kilab` Docker stack. This service uses its
**own** docker network, **own** named volume, a **non-root** user, a read-only
rootfs, `cap_drop: ALL`, `no-new-privileges`, mem/pids limits, and binds to
`127.0.0.1` only (nginx reverse-proxies a new subdomain). It shares **no** secret
with kilab. See `THREAT_MODEL.md` for why kilab stays safe even if this service
is fully compromised, and `DEPLOY.md` for the step-by-step runbook (every
server-touching command is marked **RUN THIS YOURSELF**).

## Files

```
server/
  app/
    main.py              FastAPI factory + wiring + body-size guard + /health
    schemas.py           pydantic SubmitIn / LeaderboardOut (strict; name optional)
    db.py                sqlite (WAL) DAL, parameterised queries, aggregation
    anon_name.py         deterministic anon-name generator (verbatim client copy)
    routes_submit.py     POST /submit: block-install, rate-limit, jump, store
    routes_leaderboard.py GET /leaderboard: cached aggregated board (display names)
    admin.py             block/hide/delete + /admin/* (env-token auth)
  cli.py                 local admin CLI (argparse), same auth gate
  migrations/0001_init.sql  canonical DDL (sqlite; postgres notes inline)
  migrations/0002_anti_cheat_axes.sql  ban kinds install/name + rebuild recipe
  Dockerfile             non-root, read-only-friendly, HEALTHCHECK
  docker-compose.yml     own net + own volume, least-privilege, 127.0.0.1
  nginx/telemetry.conf   NEW server-block: TLS + per-IP/per-install limits
  requirements.txt       fastapi / uvicorn / pydantic (pinned)
  .env.example           ADMIN_TOKEN / IP_HASH_SALT / limits (no real secrets)
  DEPLOY.md              exact deploy + hardening commands (run yourself)
  THREAT_MODEL.md        attacker can/can't; why kilab is safe
```

## GDPR / transparency (mirror of THREAT_MODEL.md)

Collected: a **random per-install UUID** + counters (catches, puzzles_solved,
fishing/puzzle runtime) + app version + a **salted IP hash**. **No personal
data** unless the user opts in by typing a chosen name (which only reveals that
name on the board). **No raw IP** is stored. The random id is **not** a device
fingerprint and can be rotated by editing the open-source client. Erasure by
install id or by name via admin (`delete --install|--name`).

## Run the server tests (no live box needed)

```bash
pip install -r server/requirements.txt
python -m pytest server/tests -q          # if you add the optional pytest
```
