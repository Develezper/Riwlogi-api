# Riwlogi Classifier API

FastAPI API that classifies user programming behavior using OpenAI.
It integrates with the Riwlogi Node.js backend via `CLASSIFIER_API_BASE`.

This service lives in the `api/` folder of the monorepo (formerly `classifier-api`).

## How it works

When a user submits code, the Node.js backend sends interaction events
(keys, paste, delete, runs) to this API. OpenAI analyzes the pattern and
returns whether the code was written by a human, AI-assisted, or AI-generated.

If OpenAI is unavailable or fails, the API uses a **local heuristic** as an
automatic fallback, so the Node.js backend is never affected.

---

## Installation and Startup

### Recommended option (single command)

From the `api/` folder:

```bash
make run
```

or:

```bash
./start.sh
```

This script:
- Creates `.venv` (if it doesn't exist)
- Installs dependencies from `requirements.txt`
- Creates `.env` from `.env.example` (if it doesn't exist)
- Starts `uvicorn` with `--reload`

### Manual option

```bash
# Create the virtual environment
python3 -m venv .venv

# Activate the virtual environment
source .venv/bin/activate

# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure environment variables
cp .env.example .env
# Edit .env and add your OPENAI_API_KEY

# 3. Start the server
uvicorn main:app --host 0.0.0.0 --port 8001 --reload
```

The API will be available at: `http://localhost:8001`
Interactive documentation: `http://localhost:8001/docs`

---

## Node.js Backend Configuration

Add this variable to the Riwlogi backend `.env`:

```env
CLASSIFIER_API_BASE=http://localhost:8001
```

In production, point to the URL where this API is deployed:

```env
CLASSIFIER_API_BASE=https://your-classifier-api.com
```

## Deployment on Render (Docker)

This repo includes `render.yaml` and `Dockerfile` for container deployment.
Important points:
- The service in `render.yaml` uses `env: docker` (not Python runtime).
- Render injects `PORT` automatically.
- The health check uses `GET /health`.

Required variable in Render:
- `OPENAI_API_KEY`

---

## Endpoints

### `GET /health`
Health check to verify the API is active.

```json
{ "ok": true, "status": "ok" }
```

### `POST /classify`
Classifies programming behavior.

**Request:**
```json
{
  "events": [
    { "type": "key", "char_count": 5, "timestamp": "2026-03-11T10:00:00.000Z" },
    { "type": "paste", "char_count": 320, "timestamp": "2026-03-11T10:00:05.000Z" }
  ],
  "summary": {
    "key": 40,
    "paste": 320,
    "delete": 10,
    "run": 1
  }
}
```

**Response:**
```json
{
  "label": "ai_generated",
  "confidence": 0.91
}
```

Possible `label` values:
- `"human"` — manually written code
- `"assisted"` — moderate use of AI tools / autocomplete
- `"ai_generated"` — mainly pasted / AI-generated code

### `POST /generate-problem`
Generates a complete exercise for the admin panel from a prompt.

**Request:**
```json
{
  "prompt": "Create a reverse string exercise with 3 progressive stages."
}
```

**Response (summary):**
```json
{
  "title": "Reverse String",
  "difficulty": 1,
  "tags": ["strings", "two-pointers"],
  "statement_md": "## Description ...",
  "starter_code": {
    "python": "def solve(chars): ...",
    "javascript": "function solve(chars) { ... }"
  },
  "stages": [
    {
      "stage_index": 1,
      "prompt_md": "Reverse the input array in-place.",
      "hidden_count": 2,
      "visible_tests": [
        { "input_text": "['h','e','l','l','o']", "expected_text": "['o','l','l','e','h']" }
      ]
    }
  ]
}
```

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `OPENAI_API_KEY` | *(required)* | OpenAI API Key |
| `OPENAI_MODEL` | `gpt-4o-mini` | OpenAI model to use |
| `OPENAI_GENERATION_MODEL` | `OPENAI_MODEL` | Model for the exercise generation endpoint |
| `HOST` | `0.0.0.0` | Server host |
| `PORT` | `8001` | Server port |
| `CORS_ORIGINS` | `*` | Allowed origins (comma-separated list) |

> If you start the API from the Node.js backend (autostart), you can control the host/port
> with `CLASSIFIER_API_HOST` and `CLASSIFIER_API_PORT` in the backend `.env`.

---

## Project Structure

```
api/
├── main.py          # FastAPI App, endpoints, lifespan
├── models.py        # Pydantic models (request/response)
├── classifier.py    # OpenAI logic + heuristic fallback
├── problem_generator.py # Internal prompt + exercise generation
├── requirements.txt
├── .env.example
└── README.md
```
