# Riparia — deployment runbook (Render)

Zero-assumption, ordered checklist. Follow top to bottom.

---

## 1. GitHub repository

1. Push this repo to GitHub (public).
2. Confirm `.gitignore` covers `.env`, `data/`, `__pycache__/`, `.venv/`, IDE folders — it does; verify with:
   ```bash
   git status --ignored
   ```
3. Confirm nothing sensitive is in history (audit done: clean). If you ever commit a secret: rotate it **first**, then purge history (git-filter-repo), then force-push.
4. Add the MIT LICENSE (already in repo). Check the README renders well on GitHub — it's the first thing judges open.

## 2. Render project + blueprint deploy

1. Create a Render account (render.com) → **New +** → **Blueprint**.
2. Connect your GitHub repo. Render reads `render.yaml` and proposes:
   - Web service `riparia-api` (Python, starter plan)
   - PostgreSQL `riparia-db` (basic-256mb)
3. Click **Apply** — both services provision. The first deploy will fail-safe if required secrets are unset (by design).

## 3. Environment variables (Render dashboard → riparia-api → Environment)

| Key | Value | Notes |
|---|---|---|
| `ENVIRONMENT` | `production` | set by blueprint |
| `DATABASE_URL` | auto-wired from `riparia-db` | set by blueprint |
| `SESSION_SECRET` | auto-generated | set by blueprint |
| `GEMINI_API_KEY` | your Google AI Studio key | free tier is fine |
| `REVIEWER_PASSWORD_HASH` | bcrypt hash of your reviewer password | generate: `py -c "import bcrypt;print(bcrypt.hashpw(b'YOUR-PASSWORD',bcrypt.gensalt(12)).decode())"` |
| `REVIEWER_USERNAME` | your reviewer username | default `reviewer` |
| `R2_ACCOUNT_ID` / `R2_ACCESS_KEY_ID` / `R2_SECRET_ACCESS_KEY` / `R2_BUCKET` | from step 4 | leave empty to run with local-disk photos until R2 is ready |
| `PUBLIC_BASE_URL` | `https://<your-render-app>.onrender.com` | update to your final domain after DNS |
| `ALLOWED_ORIGINS` | `https://<your-render-app>.onrender.com` | comma-separated; no wildcards |

4. **Manual deploy** after setting vars — the app refuses to boot in production without `SESSION_SECRET` + a Postgres `DATABASE_URL` (guard in `app/config.py`).

## 4. Cloudflare R2 (photo storage)

1. Cloudflare dashboard → R2 → **Create bucket** (name e.g. `riparia-photos`) — region auto.
2. R2 → **Manage API tokens** → create token with **Object Read & Write** on the bucket. Note Access Key ID / Secret.
3. Note your **account ID** (dash URL) → that's `R2_ACCOUNT_ID`.
4. Bucket stays **private** — no public access, no custom domain needed (photos are served via signed URLs).
5. Put the four values into Render env vars (step 3) and redeploy.

## 5. Database migrations

- The blueprint's build command runs `alembic upgrade head` on every deploy — migrations are automatic.
- To run manually: Render shell (or a one-off job):
  ```bash
  alembic upgrade head
  ```

## 6. Domain + DNS (optional but recommended)

1. Buy the domain (Porkbun/Cloudflare Registrar).
2. Render → riparia-api → Settings → **Custom Domains** → add your domain.
3. At your registrar, create the DNS records Render shows (usually a CNAME to your `onrender.com` host, or ALIAS/ANAME at apex).
4. Wait for propagation; Render issues TLS automatically (Let's Encrypt). Confirm the padlock.
5. Update `PUBLIC_BASE_URL` + `ALLOWED_ORIGINS` to the final domain and redeploy.

## 7. Pre-submission verification on the LIVE URL

Work through this exact list on the production URL (not localhost):

- [ ] `https://<host>/api/health` → `{"status":"ok"}`
- [ ] Landing page loads, dark mode toggle works, no console errors
- [ ] `/submit.html`: submit a real photo + description → success panel with confidence meter + indicators
- [ ] Upload a non-image (e.g. renamed .txt) → clean 400 error message, no crash
- [ ] `/dashboard.html` redirects to login when signed out
- [ ] Login with reviewer credentials → queue shows the submission
- [ ] Approve → verdict shows FHIR id; click through to the FHIR server and confirm the resource
- [ ] Reject a second submission → no FHIR call (rejected items show no FHIR id)
- [ ] `/docs` renders the OpenAPI page
- [ ] Response headers include CSP, X-Frame-Options, nosniff (DevTools → Network)
- [ ] Mobile: complete the full submit → review flow on a phone viewport
- [ ] Lighthouse: ≥90 accessibility on landing + submit

## 8. Devpost submission

- **Live URL first**: `https://<your-domain>` (or the onrender.com URL) — judges click this before anything else.
- **GitHub repo second** — pinned README, clean commit history, green Actions badge:
  `![CI](https://github.com/<you>/<repo>/actions/workflows/ci.yml/badge.svg)`
- In the submission text, link both plus `/docs` (OpenAPI) and one approved FHIR resource URL as proof of interoperability.
- Keep the demo video on the live site, not localhost — it doubles as evidence the deployment is real.
