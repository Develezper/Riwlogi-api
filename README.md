# Riwlogi Classifier API

A FastAPI-based service designed to analyze user programming behavior and generate automated development exercises.

The project has two main objectives:
*   **Authorship Detection:** Classifies whether code was written by a human, assisted by AI (e.g., Copilot), or entirely AI-generated, based on keyboard biometrics (typing, pasting, deleting, etc.) and code stylometry.
*   **Problem Generation:** Creates structured programming challenges (statement, starter code in multiple languages, and test cases) from a user prompt.

This service integrates with the Riwlogi Node.js backend via `CLASSIFIER_API_BASE`.

---

## Features

- **Hybrid Classification:** Uses OpenAI's advanced models (e.g., `gpt-4o-mini`) to analyze the last 50 relevant events and up to 4,000 characters of code.
- **Local Heuristic Fallback:** If the AI service is unavailable, a local heuristic based on `paste_ratio` (the ratio between pasted and typed text) provides an automatic fallback.
- **Automated Problem Generation:** Generates complex JSON objects including titles, difficulty levels, Markdown statements, and unit tests for Python, JavaScript, and TypeScript.
- **Ready for Production:** Docker-ready and optimized for deployment on platforms like Render.

---

## Tech Stack

- **Framework:** [FastAPI](https://fastapi.tiangolo.com/) (Python 3.11+)
- **Server:** [Uvicorn](https://www.uvicorn.org/)
- **AI Integration:** [OpenAI API](https://openai.com/api/)
- **Validation:** [Pydantic v2](https://docs.pydantic.dev/latest/)
- **Deployment:** Docker & Makefile automation

---

## Installation and Startup

### Recommended (One Command)

From the project root:

```bash
make run
```

or:

```bash
./start.sh
```

This script will:
- Create a `.venv` (if it doesn't exist).
- Install dependencies from `requirements.txt`.
- Copy `.env.example` to `.env` (if it doesn't exist).
- Start the `uvicorn` server with `--reload`.

### Manual Installation

1. **Create and activate a virtual environment:**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure environment variables:**
   ```bash
   cp .env.example .env
   # Edit .env and add your OPENAI_API_KEY
   ```

4. **Start the server:**
   ```bash
   uvicorn main:app --host 0.0.0.0 --port 8001 --reload
   ```

The API will be available at: `http://localhost:8001`
Interactive documentation: `http://localhost:8001/docs`

---

## API Endpoints

### `GET /health`
Health check to verify the service status.
**Response:** `{ "ok": true, "status": "ok" }`

### `POST /classify`
Classifies the programming behavior based on interaction events and source code.
**Request Body:**
```json
{
  "events": [...],
  "summary": {
    "key": 40,
    "paste": 320,
    "delete": 10,
    "run": 1
  },
  "code": "..."
}
```
**Response:**
```json
{
  "label": "human" | "assisted" | "ai_generated",
  "confidence": 0.95
}
```

### `POST /generate-problem`
Generates a complete programming exercise for the admin panel from a prompt.
**Request Body:**
```json
{
  "prompt": "Create a string manipulation exercise."
}
```
**Response:** A detailed JSON object containing `title`, `difficulty`, `tags`, `statement_md`, `starter_code`, and `stages` with test cases.

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `OPENAI_API_KEY` | *(Required)* | Your OpenAI API Key |
| `OPENAI_MODEL` | `gpt-4o-mini` | OpenAI model for classification |
| `OPENAI_GENERATION_MODEL` | `gpt-4o-mini` | OpenAI model for problem generation |
| `HOST` | `0.0.0.0` | Server host |
| `PORT` | `8001` | Server port |
| `CORS_ORIGINS` | `*` | Allowed CORS origins (comma-separated list) |

---

## Project Structure

```text
.
├── main.py              # FastAPI entry point & endpoints
├── classifier.py        # OpenAI classification logic & heuristics
├── problem_generator.py # Logic for generating coding challenges
├── models.py            # Pydantic data models
├── Makefile             # Automation for common tasks
├── Dockerfile           # Containerization setup
├── README.md            # You are here
└── requirements.txt     # Python dependencies
```

---

## Deployment on Render (Docker)

This repository includes `render.yaml` and a `Dockerfile`.
- Render uses `env: docker`.
- The `PORT` is automatically injected by Render.
- Health checks use `GET /health`.
- Remember to set `OPENAI_API_KEY` in the Render environment settings.
