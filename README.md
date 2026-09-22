# Riparia

**AI-supported validation middleware for citizen freshwater ecosystem observations.**

Riparia sits behind citizen-science channels and turns raw citizen photos into trustworthy, standards-compliant health data — with a human always in the loop.

[![CI](https://img.shields.io/github/actions/workflow/status/samuel-cyber/StreamCheck/ci.yml?branch=main)](../../actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)

**🔗 Live demo:** [riparia-api.onrender.com](https://riparia-api.onrender.com)
**📚 API docs:** [riparia-api.onrender.com/docs](https://riparia-api.onrender.com/docs)

---

## Table of contents

- [Overview](#overview)
- [The problem](#the-problem)
- [How it works](#how-it-works)
- [Architecture](#architecture)
- [Tech stack](#tech-stack)
- [Getting started](#getting-started)
- [Environment variables](#environment-variables)
- [Testing](#testing--checks)
- [Repository layout](#repository-layout)
- [Deployment](#deployment)
- [Security](#security)
- [Research & citations](#research--citations)
- [License](#license)

---

## Overview

Riparia is a middleware validation layer — not a replacement for an existing citizen-science app, but a layer that sits *behind* one. It takes a citizen's photo and description, assesses it with AI against real published ecological indicators, requires human sign-off before anything is finalized, and outputs a standards-compliant HL7 FHIR `Observation` that any municipal or public-health system can ingest.

Built for the **OneAquaHealth IEEE Global Hackathon** (Track 3: AI-Supported Assessment).

## The problem

Citizen-science water monitoring has two structural gaps:

1. **Signal quality** — citizens often don't know which visual signs are scientifically meaningful, and report vague impressions rather than the specific indicators researchers track
2. **Data silos** — even good citizen data stays trapped in app-specific formats, disconnected from the standardized formats (HL7 FHIR) that health systems actually use

Riparia addresses both: it teaches the assessment step what to look for, and it teaches the output step how to speak the language public-health systems already understand.

## How it works

```
1. Citizen submits a photo + description
2. AI assesses it against 4 known indicators → confidence score + plain-language reasoning
3. Submission enters a review queue (visible only to an authenticated reviewer)
4. Reviewer approves  → mapped to a FHIR Observation → posted to a FHIR server
   Reviewer rejects   → discarded, nothing committed
```

Every submission is explainable — the AI never just returns a verdict, it returns *why*, so the human reviewer has something real to evaluate.

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

## Tech stack

| Layer | Choice | Why |
|---|---|---|
| API | FastAPI (Python 3.11+) | typed validation, free OpenAPI docs, async where it matters |
| Database | PostgreSQL (Render managed) | production-grade, backed up; SQLite for local dev |
| Migrations | Alembic | versioned schema, runs automatically on deploy |
| AI | Gemini vision (`google-genai`) | one well-prompted call, strict output sanitization, retry with backoff |
| Photo storage | Cloudflare R2 (S3-compatible) | private bucket, zero egress fees, signed-URL delivery |
| Auth | bcrypt + signed session cookies + CSRF | small, auditable surface — no third-party identity dependency |
| Frontend | Static HTML/CSS/JS | zero build step, dark-mode design tokens |
| Hosting | Render | web service + managed Postgres via one `render.yaml` Blueprint |

## Getting started

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure environment
cp .env.example .env      # macOS/Linux
copy .env.example .env    # Windows
# fill in what you have — the app degrades gracefully without any of it

# 3. Run the server
uvicorn app.main:app --reload --port 8000
```

Then visit:

| Page | URL |
|---|---|
| Landing page | http://localhost:8000/ |
| Citizen submission form | http://localhost:8000/submit.html |
| Reviewer console | http://localhost:8000/dashboard.html |
| API docs (OpenAPI) | http://localhost:8000/docs |

Dev reviewer login: `reviewer` / `reviewer-dev-password` — **never used in production**, see [Security](#security).

Without a `GEMINI_API_KEY`, the AI pipeline runs in a deterministic keyword-based preview mode. Without R2 credentials, photos are stored locally under `data/` (gitignored). **Nothing external is required to run the full stack locally.**

## Environment variables

| Variable | Required? | Default | Notes |
|---|---|---|---|
| `ENVIRONMENT` | No | `development` | Set to `production` on deploy — enforces real secrets are set |
| `DATABASE_URL` | Prod only | SQLite (dev) | Render provides this automatically for the managed Postgres instance |
| `GEMINI_API_KEY` | No | — | Without it, runs in mock/preview AI mode |
| `GEMINI_MODEL` | No | `gemini-flash-latest` | |
| `FHIR_BASE_URL` | No | Public HAPI test server | Point at a self-hosted instance if you have one |
| `R2_ACCOUNT_ID` / `R2_ACCESS_KEY_ID` / `R2_SECRET_ACCESS_KEY` / `R2_BUCKET` | No | — | Without these, photos fall back to local disk storage |
| `SESSION_SECRET` | Prod only | — | Must be a long random value in production |
| `REVIEWER_USERNAME` | No | `reviewer` | |
| `REVIEWER_PASSWORD_HASH` | Prod only | dev-only bcrypt hash | **Must be replaced before deploying** |
| `PUBLIC_BASE_URL` / `ALLOWED_ORIGINS` | Prod only | `http://localhost:8000` | Set to your real deployed URL |

See `.env.example` for the full annotated template.

## Testing & checks

```bash
ruff check app migrations tests      # lint
pytest -q                            # test suite
python scripts/test_fhir_mapping.py  # sanity-check a FHIR payload against the live server
```

CI runs lint and tests automatically on every push via GitHub Actions (`.github/workflows/ci.yml`).

## Repository layout

```
├── app/
│   ├── main.py            # API v1 routes, middleware, static file serving
│   ├── config.py          # typed settings, env-driven
│   ├── db.py               # engine + sessions (SQLite dev / Postgres prod)
│   ├── models.py           # Observation model + indexes
│   ├── ai.py               # Gemini assessment pipeline
│   ├── fhir.py              # FHIR mapping + HTTP client
│   ├── storage.py           # R2 signed-URL photo storage
│   ├── photo_sanitizer.py   # upload hardening (content sniffing, EXIF strip, re-encode)
│   └── auth.py              # reviewer sessions + CSRF
├── migrations/              # Alembic migrations
├── static/                  # landing page, submission form, dashboard, login
├── tests/                   # pytest test suite
├── scripts/                 # standalone diagnostic scripts
├── render.yaml               # Render Blueprint (web service + Postgres)
└── .github/workflows/        # CI (ruff + pytest)
```

## Deployment

Full infrastructure is defined declaratively in [`render.yaml`](render.yaml) — see [DEPLOYMENT.md](DEPLOYMENT.md) for the complete step-by-step deploy runbook (Render, Postgres, object storage, environment variables, and live verification).

## Security

- Session-based reviewer auth (bcrypt + signed HttpOnly cookies) gating every state-changing endpoint
- CSRF tokens required on all approve/reject actions
- Upload hardening: magic-byte content sniffing, decompression-bomb size ceiling, EXIF/GPS metadata stripped from every photo before storage
- Rate limiting on public endpoints, narrow CORS, security headers (CSP, HSTS in production)
- Secrets read from environment variables only — see [SECURITY.md](SECURITY.md) for the full pre-launch security review and disclosed limitations

## Research & citations

The AI assessment indicators are grounded in OneAquaHealth's own published findings:

- da Silva et al., "Patterns of pharmaceutical contamination in streams of European cities across urbanisation gradients," *Journal of Hazardous Materials* (2025) — pharmaceuticals detected in 91% of monitored urban stream sites
- OneAquaHealth Policy Brief, *"Urban Stream Ecosystem Health as a One Health Priority"* (2026) — identifies artificial light at night, loss of riparian vegetation, and diatom deformities as key indicators of urban stream degradation

## License

MIT — see [LICENSE](LICENSE).