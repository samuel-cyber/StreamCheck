# Riparia

**Validation middleware for citizen freshwater observations — from citizen photos to public-health intelligence.**

Riparia sits behind citizen-science channels (the submission form here, or a partner app) and turns raw observations into trustworthy, interoperable health data:

1. **AI assessment** — every submission is analyzed against published OneAquaHealth urban-stream indicators, returning detected indicators, a confidence score, and a plain-language rationale.
2. **Human confirmation** — reviewers see the evidence and the AI's reasoning; nothing is committed without a person's decision.
3. **Standards-grade output** — approved observations are committed as HL7 FHIR `Observation` resources, readable by municipal and public-health systems.

---

## Architecture

```
Citizen submission ──▶ Upload sanitizer ──▶ AI assessment (Gemini vision)
                              │                      │
                              ▼                      ▼
                      Object storage (R2)      Pending observation (PostgreSQL)
                                                     │
                                             Reviewer console (session auth)
                                                     │ approve
                                                     ▼
                                        HL7 FHIR Observation ──▶ FHIR server
```

| Layer | Choice | Why |
|---|---|---|
| API | FastAPI (Python 3.11+) | typed validation, OpenAPI docs, async where it matters |
| DB | PostgreSQL (Render managed) | managed, backed up; SQLite for local dev |
| Migrations | Alembic | versioned schema, runs on deploy |
| AI | Gemini vision (`google-genai`) | single well-prompted call; strict output sanitization |
| Photos | Cloudflare R2 (S3 API) | private bucket, zero egress fees, signed-URL delivery |
| Auth | bcrypt + signed session cookies + CSRF | small auditable surface, no third-party identity dependency |
| Frontend | Static HTML/CSS/JS | zero build step; design-token system with dark mode |

## Repository layout

```
├── app/
│   ├── main.py            # API v1, middleware, static serving
│   ├── config.py          # typed settings (env-driven)
│   ├── db.py              # engine + sessions (SQLite dev / Postgres prod)
│   ├── models.py          # Observation model + indexes
│   ├── ai.py              # Gemini assessment pipeline
│   ├── fhir.py            # FHIR mapping + HTTP client
│   ├── storage.py         # R2 signed-URL photo storage
│   ├── photo_sanitizer.py # upload hardening (sniff, strip EXIF, re-encode)
│   └── auth.py            # reviewer sessions + CSRF
├── migrations/            # Alembic
├── static/                # landing, submit, dashboard, login
├── tests/                 # pytest API tests
├── scripts/               # standalone FHIR payload test
├── render.yaml            # Render blueprint (web + Postgres)
└── .github/workflows/     # CI (ruff + pytest)
```

## Local development

```bash
py -m pip install -r requirements.txt
copy .env.example .env          # fill in what you have; everything degrades gracefully
py -m uvicorn app.main:app --reload --port 8000
```

- Landing page: http://localhost:8000/
- Citizen form: http://localhost:8000/submit.html
- Reviewer console: http://localhost:8000/dashboard.html (dev login `reviewer` / `reviewer-dev-password`)
- API docs: http://localhost:8000/docs

Without a `GEMINI_API_KEY` the AI pipeline runs in deterministic preview mode; without R2 keys photos are stored under `data/` (gitignored). Nothing external is required to run the stack.

## Tests & checks

```bash
py -m ruff check app migrations tests
py -m pytest -q
py scripts/test_fhir_mapping.py    # static FHIR payload against the live FHIR server
```

## Deployment

Full blueprint in `render.yaml` — see [DEPLOYMENT.md](DEPLOYMENT.md) for the complete step-by-step runbook (Render, Postgres, R2, DNS, verification).

Security posture and known limitations: [SECURITY.md](SECURITY.md)

## License

MIT — see [LICENSE](LICENSE).
