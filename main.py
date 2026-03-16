import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(dotenv_path=BASE_DIR / ".env")
load_dotenv(dotenv_path=BASE_DIR / ".env.local", override=True)

from classifier import classify
from models import (
    ClassifyRequest,
    ClassifyResponse,
    GenerateProblemRequest,
    GenerateProblemResponse,
)
from problem_generator import generate_problem

# ── Logging ──────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger(__name__)


# ── App ───────────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    api_key_set = bool(os.getenv("OPENAI_API_KEY"))
    logger.info("Classifier API starting — model=%s api_key_set=%s", model, api_key_set)
    yield
    logger.info("Classifier API shutting down.")


app = FastAPI(
    title="Riwlogi Classifier API",
    description="Clasifica comportamiento de programación usando OpenAI.",
    version="1.0.0",
    lifespan=lifespan,
)

cors_origins_env = os.getenv("CORS_ORIGINS", "*")
cors_origins = [item.strip() for item in cors_origins_env.split(",") if item.strip()]
if not cors_origins:
    cors_origins = ["*"]

allow_all = "*" in cors_origins

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if allow_all else cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Global exception handler ──────────────────────────────────────────────────

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error("Unhandled exception: %s", exc, exc_info=True)
    if request.url.path == "/classify":
        # Only classification should degrade to a successful fallback.
        return JSONResponse(
            status_code=200,
            content={"label": "human", "confidence": 0.55},
        )

    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health", tags=["Health"])
async def health():
    return {"ok": True, "status": "ok"}


@app.post("/classify", response_model=ClassifyResponse, tags=["Classifier"])
async def classify_endpoint(request: ClassifyRequest):
    """
    Recibe eventos de interacción del backend Node.js y devuelve
    la clasificación del comportamiento: human, assisted o ai_generated.
    """
    result = await classify(request)
    logger.info("classify → label=%s confidence=%s", result.label, result.confidence)
    return result


@app.post("/generate-problem", response_model=GenerateProblemResponse, tags=["Generator"])
async def generate_problem_endpoint(request: GenerateProblemRequest):
    """
    Genera un ejercicio completo a partir de un prompt para el panel admin.
    """
    try:
        result = await generate_problem(request)
    except RuntimeError as exc:
        logger.warning("generate-problem failed: %s", exc)
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    logger.info("generate-problem → title=%s difficulty=%s", result.title, result.difficulty)
    return result


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8001"))
    uvicorn.run("main:app", host=host, port=port, reload=True)
