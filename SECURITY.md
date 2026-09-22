# Riparia — pre-launch security review

**Scope:** StreamCheck → Riparia v1.0 (FastAPI backend, static frontend, R2 object storage, HAPI FHIR integration)
**Reviewer:** engineering (pre-deployment)
**Status:** all items below implemented and verified in code

---

## 1. Authentication & session management

| Item | Status | Detail |
|---|---|---|
| Reviewer auth required on `/api/v1/queue` | ✅ | `Depends(require_reviewer)` — returns 401 without a valid session |
| Reviewer auth required on approve/reject | ✅ | Session **and** CSRF token required; 401 vs 403 distinguished |
| Password storage | ✅ | bcrypt, cost 12; hash supplied via `REVIEWER_PASSWORD_HASH` env var — never in code |
| Session cookie flags | ✅ | HttpOnly, `SameSite=Lax`, `Secure` in production, 12h expiry, signed with `SESSION_SECRET` (itsdangerous TimestampSigner) |
| CSRF protection | ✅ | Token minted inside the signed session cookie; approve/reject require `X-CSRF-Token` header; constant-time comparison |
| Login rate limiting | ✅ | `5/minute` per IP via slowapi — credential-stuffing brake |
| Production secret guard | ✅ | App refuses to boot in production without a real `SESSION_SECRET` and a non-SQLite `DATABASE_URL` |

## 2. File upload security

| Item | Status | Detail |
|---|---|---|
| Content-type validation | ✅ | Magic-byte sniffing (`photo_sanitizer.sniff_type`) — declared MIME is never trusted |
| Size limit (server-side) | ✅ | 10 MB hard cap before parsing |
| Malformed/polyglot payload scan | ✅ | Full Pillow decode + `Image.load()`; decompression-bomb ceiling at ~40 MP |
| EXIF / GPS metadata removal | ✅ | Images are re-encoded pixel-by-pixel into a fresh buffer — all metadata dropped. Citizen GPS coordinates never leave the device |
| Normalized re-encode | ✅ | Stored files are clean JPEG/PNG produced server-side |

## 3. Rate limiting & abuse control

| Endpoint | Limit | Why |
|---|---|---|
| `POST /api/v1/observations` | 10/min/IP | AI-cost abuse + spam brake |
| `POST /api/v1/auth/login` | 5/min/IP | Brute force |
| Default | 120/min/IP | General abuse ceiling |

429 responses use the standard error envelope with `Retry-After`.

## 4. Input validation

- `text_description`: 3–2000 chars, enforced server-side by FastAPI Form constraints.
- All user/AI strings rendered in the frontend go through `escapeHtml()` before insertion (`innerHTML`); no raw interpolation anywhere.
- Query params (`status`, `limit`, `offset`) validated by typed FastAPI Query constraints.
- AI output is sanitized: unknown indicator strings are stripped from structured data (and disclosed in the reasoning text), confidence clamped to [0,1].

## 5. Transport & headers

| Header | Value / policy |
|---|---|
| `Content-Security-Policy` | `default-src 'self'`; scripts self-only (no inline script sources in HTML files); styles limited to self + Google Fonts; `frame-ancestors 'none'` |
| `X-Content-Type-Options` | `nosniff` |
| `X-Frame-Options` | `DENY` |
| `Referrer-Policy` | `strict-origin-when-cross-origin` |
| `Permissions-Policy` | camera, geolocation, microphone disabled |
| `Strict-Transport-Security` | 1 year, includeSubDomains — production only |
| CORS | Explicit origin allow-list from `ALLOWED_ORIGINS`; never `*`; credentials enabled only for those origins; methods limited to GET/POST |

## 6. Secrets management

- All secrets via environment: `GEMINI_API_KEY`, `SESSION_SECRET`, `REVIEWER_PASSWORD_HASH`, `DATABASE_URL`, R2 keys.
- `.env` gitignored; `.env.example` committed with placeholders only.
- `render.yaml` uses `generateValue: true` for `SESSION_SECRET` and `sync: false` for all secrets — they exist only in Render's encrypted env store.
- Repo audit: git history contains **no** `.env`, no database file, no photos, no API keys. No history purge required.
- No secret is ever sent to the client: photos are served via server-minted signed URLs; API keys stay server-side.

## 7. Data protection

- Photos stored in a **private** R2 bucket; access only through 1-hour signed URLs.
- Local dev fallback writes under `data/` (gitignored).
- SQLite dev DB gitignored; production uses managed PostgreSQL with TLS.
- PII exposure minimized: no citizen identity is collected or stored at all (no accounts on the citizen path).

## 8. Dependencies

Pinned exact versions (`requirements.txt`) — reproducible builds, no silent minor-version drift:

| Package | Pinned | Notes |
|---|---|---|
| fastapi / starlette | 0.141.1 / 1.6.0 | current; no known open CVEs at pin time |
| pillow | 12.3.0 | current major; image-parsing CVEs from older lines (≤10.x) not present |
| python-multipart | 0.0.32 | current; earlier releases had DoS advisories — pinned past them |
| boto3 / botocore | 1.43.99 | current |
| bcrypt / itsdangerous | 5.0.0 / 2.2.0 | current |
| google-genai | 2.24.0 | current |
| uvicorn | 0.53.0 | current |

Run `pip-audit` in CI before submission for a point-in-time CVE sweep (workflow file includes lint + tests; add `pip-audit` as a follow-up job if desired).

## 9. Known limitations (disclosed, not hidden)

1. **Single reviewer account** — appropriate for launch scale; multi-user RBAC is a roadmap item. Rate-limited login keeps the attack surface small.
2. **slowapi limiter is in-process** — per-worker limits on multi-worker deploys. Acceptable at this scale; Redis-backed shared limiter is the production upgrade path.
3. **HAPI public test server** is a shared demo instance — fine for demonstration; a dedicated FHIR server (HAPI via Docker on Render) is the real-deployment step.
4. Session revocation is passive (12h expiry); a server-side session store would allow instant revocation.
