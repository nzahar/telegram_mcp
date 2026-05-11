# Roadmap

Post-v1 work, in rough order of likely execution. Each stage gets its own branch and full plan file in `docs/plans/<branch-slug>.md` when it starts; until then this is the agreed-upon scope and the locked decisions to date.

## Stage 2 — HTTP transport + remote deploy

**Status:** drafted, not yet branched. Awaiting spec lock-in session.

**Goal.** Add an HTTP transport mode to the MCP server so it can run as a long-lived service on a cloud host and be reached by remote MCP clients (Cowork, Claude Code on the web, future hosts), without dropping the stdio mode that v1 already supports for local use.

### Already-locked decisions

- **A dedicated Telegram account** will be used for the deployed server. No personal chats accessible from the session string the cloud host holds. This is the primary mitigation for the credential-on-cloud risk discussed at the v1 → v2 hand-off — a compromised deploy at worst exposes a purpose-built account, not a personal one.
- **Stdio transport stays.** HTTP is opt-in, selected by an env var (working name: `MCP_TRANSPORT=stdio|http`). Local development and tests keep using stdio. The same binary serves both modes.
- **The five hard invariants from `CLAUDE.md` carry over.** ADR-0001 (no whitelist), ADR-0002 (no stdout writes — though HTTP mode adds stderr-clean as a softer constraint), ADR-0003 (caller-owned MarkdownV2), and ADR-0004 (`since` required) all hold in HTTP mode. HTTP mode adds new constraints (auth required, TLS required, secrets via platform store), it does not weaken existing ones.

### Open for the spec session

These are the decisions we'll lock in before the branch starts. Each becomes a row in the new plan's "Decisions" table.

| Question | Candidate answers | Notes |
|---|---|---|
| Hosting platform | Fly.io / Railway / GitHub Codespace + cloudflared / own VPS | See discussion in session transcript; Fly.io is the current top candidate. Cost ~$2/mo. |
| Auth model | Bearer token / API key / OAuth / mTLS | Bearer token is the FastMCP-default and matches Cowork's expected shape. |
| Read-only mode? | yes / no | Should `send_to_self` be exposed remotely at all, or restricted to local stdio? A remote `send_to_self` enables drive-by abuse if the bearer token leaks. |
| CI/CD trigger | push to main / git tag / manual | Push-to-main is simple but couples deploy to merge cadence; tags are explicit. |
| Secret management | Platform secrets (fly secrets) / SOPS-encrypted file / Vault | Platform secrets are simplest and don't add infra. |
| Observability | Existing file logger only / + metrics endpoint / + structured JSON logs | Add only if free / cheap. |
| Health check | `/health` endpoint / TCP ping / process check | Most platforms need an HTTP health probe. |

### Likely shape (subject to spec session)

Sketch — not committed. The actual plan will be written when the branch opens.

1. **`server.py` transport switch.** Read `MCP_TRANSPORT` env (default `stdio`). For `http`, call `mcp.run(transport="streamable-http", host=..., port=..., show_banner=False)`. ~10 lines.
2. **Bearer-token auth middleware** (FastMCP-native, HTTP mode only). The token comes from env (`MCP_AUTH_TOKEN`). Requests without the matching `Authorization: Bearer <token>` header are rejected with 401 before they reach `_CallLoggingMiddleware`.
3. **`/health` endpoint.** Returns 200 with a tiny JSON `{"status": "ok"}`. Used by the platform's liveness probe. Does NOT touch Telethon (so a Telegram outage doesn't restart the container).
4. **Dockerfile** — multi-stage uv build. ~30 lines.
5. **Platform config** — `fly.toml` (if Fly) or equivalent. Sets the env vars, the secrets, the health check path, the restart policy.
6. **GitHub Actions workflow.** Deploys on the chosen trigger. Stores the platform deploy token in GitHub Secrets.
7. **ADR-0005** — documents the HTTP transport decision, the auth model, the deploy topology, the secret-management chain.
8. **ADR-0006 (optional)** — documents the dedicated-TG-account practice if it deserves its own record beyond a roadmap line.
9. **README update** — adds a "Register in MCP host (remote)" subsection alongside the existing stdio block. URL + bearer-token-header config example.
10. **`docs/SETUP.md` update** — adds a "Connecting to the deployed server" section.
11. **Tests** — new test that the `/health` endpoint returns 200 without auth; new test that protected endpoints return 401 without the bearer token; preserve all 138 existing tests (HTTP mode should not alter stdio mode's behaviour).

### Trigger

The user signals readiness to start the branch ("давай начнём deploy", "open the http-deploy branch", or equivalent). Until then, this entry exists as memory of the agreed scope; no code is written.

Spec session goes first (workflow step 1 — clarify open questions with the user), then plan file at `docs/plans/<branch-slug>.md`, then plan-reviewer, then implementation.
