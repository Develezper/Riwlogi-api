import logging
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

load_dotenv()

from classifier import classify
from models import ClassifyRequest, ClassifyResponse

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


# ── Exception handler global ─────────────────────────────────────────────────

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error("Unhandled exception: %s", exc, exc_info=True)
    # Devolvemos fallback en lugar de 500 para no romper el backend Node.js
    return JSONResponse(
        status_code=200,
        content={"label": "human", "confidence": 0.55},
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


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8001"))
    uvicorn.run("main:app", host=host, port=port, reload=True)
