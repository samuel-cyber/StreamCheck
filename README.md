# StreamCheck

**AI-Supported Freshwater Stream Assessment — Middleware Validation Layer**

Built for the [OneAquaHealth IEEE Global Hackathon](https://devpost.com) (Track 3: AI-Supported Assessment).

---

## What is StreamCheck?

StreamCheck is a middleware validation layer that sits behind citizen science apps like OneAquaHealth's. It:

1. **Assesses** citizen-submitted photos + text against specific ecological indicators using AI (Gemini vision model)
2. **Explains** the assessment in plain language — confidence score + reasoning trail
3. **Standardizes** approved observations into HL7 FHIR Observations
4. **Requires human approval** — AI assists, a person decides

> *"Use AI responsibly to support stream assessment without replacing human judgment."* — Track 3 framing

---

## Quick Start

### 1. Install dependencies

```bash
py -m pip install -r requirements.txt
```

### 2. Configure (optional)

```bash
copy .env.example .env
```

Set `GEMINI_API_KEY` to enable real AI assessment. Without it, the app runs in mock mode with keyword-based fake AI output.

### 3. Start the server

```bash
py -m uvicorn app.main:app --reload --port 8000
```

### 4. Open the apps

- **Citizen form:** http://localhost:8000/
- **Reviewer dashboard:** http://localhost:8000/dashboard.html

### 5. Demo the full flow

1. Submit a photo + description on the citizen form
2. Open the reviewer dashboard, see the AI's assessment
3. Click Approve → observation is mapped to FHIR and POSTed to the HAPI server
4. Click Reject → observation is marked rejected, nothing sent to FHIR

---

## Running a local FHIR server (optional)

For the demo, StreamCheck posts to the public HAPI test server at `https://hapi.fhir.org/baseR4`. To run your own:

```bash
docker compose up -d
# Then set FHIR_BASE_URL=http://localhost:8080/fhir in your .env
```

---

## Architecture

```
Citizen Science App
       │
       ▼
┌──────────────┐    ┌────────────────┐    ┌──────────────┐
│  POST        │    │  AI Assessment  │    │  HAPI FHIR   │
│  /observations│───▶│  (Gemini API)  │    │  Server      │
│  (photo+text)│    │  → indicators   │    │  (Observation│
└──────────────┘    │  → confidence   │    │   resource)  │
                    │  → reasoning    │    └──────┬───────┘
                    └───────┬────────┘           │
                            │ pending             │
                            ▼                     │
                    ┌───────────────┐             │
                    │   Reviewer    │             │
                    │   Dashboard   │─────────────┘
                    │  ✓ Approve    │   (on approval:
                    │  ✗ Reject     │    FHIR POST)
                    └───────────────┘
```

### Ecological Indicators

StreamCheck evaluates submissions against these specific indicators (from OneAquaHealth research):

| Indicator | What it means |
|---|---|
| Riparian vegetation degradation | Loss of streamside plant cover — habitat loss, erosion risk |
| Artificial light at night | Light pollution near water — disrupts aquatic ecosystems |
| Trash or debris | Visible pollution — physical hazard, contamination risk |
| Chemical/pharmaceutical contamination | Unusual color, foam, odor — potential health hazard |

### FHIR Compliance

Approved observations are mapped to standard HL7 FHIR `Observation` resources with:
- Valid resource structure (`resourceType`, `status`, `code`, `valueString`, `component`, `note`, `effectiveDateTime`)
- Posted to a HAPI FHIR server (real compliance, not a simulated schema)
- Resource IDs stored back on the local observation record

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `GEMINI_API_KEY` | *(empty — mock mode)* | Google Gemini API key for AI assessment |
| `GEMINI_MODEL` | `gemini-2.0-flash` | Gemini model to use |
| `FHIR_BASE_URL` | `https://hapi.fhir.org/baseR4` | FHIR server base URL |
| `PUBLIC_BASE_URL` | `http://localhost:8000` | Public URL for photo links |

---

## Tech Stack

- **Backend:** Python 3.11+ / FastAPI / SQLite / SQLModel
- **AI:** Google Gemini (vision + text) via `google-genai` SDK
- **Standards:** HL7 FHIR via HAPI FHIR server
- **Frontend:** Plain HTML + vanilla JS (zero build step)

---

## Project Structure

```
streamcheck/
├── app/
│   ├── main.py          # FastAPI routes + static file serving
│   ├── models.py        # SQLite data model (Observation)
│   ├── ai.py            # Gemini AI service + mock mode
│   ├── fhir.py          # FHIR mapping + HAPI client
│   └── config.py        # Environment configuration
├── static/
│   ├── index.html       # Citizen submission form
│   └── dashboard.html   # Reviewer dashboard
├── data/                # SQLite DB + uploaded photos (gitignored)
├── docker-compose.yml   # HAPI FHIR server config
├── requirements.txt
└── README.md
```

---

## Why This Wins (Judging Criteria)

- **Impact & Alignment:** Grounded in OneAquaHealth's real published indicators; augments existing infrastructure
- **Innovation:** Validates + standardizes citizen data into FHIR — most entrants build another reporting app
- **Architecture:** Real FHIR compliance via HAPI server demonstrates technical rigor
- **UX:** The reviewer dashboard has exactly one job — "AI supports, human decides" — visible in every card
- **Scale:** Framed as adoptable middleware any municipality could plug in

---

## License

Hackathon prototype — not for production use.
