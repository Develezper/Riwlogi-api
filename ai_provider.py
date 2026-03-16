"""
ai_provider.py — Capa de abstracción para proveedores de IA (OpenAI / Gemini).

Uso:
    from ai_provider import chat_completion, has_any_provider

    raw_json = await chat_completion(
        messages=[
            {"role": "system", "content": "..."},
            {"role": "user",   "content": "..."},
        ],
        max_tokens=100,
        temperature=0.1,
        json_mode=True,
    )
"""

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

# ── Constantes ────────────────────────────────────────────────────────────────

PROVIDER_OPENAI = "openai"
PROVIDER_GEMINI = "gemini"
PROVIDER_AUTO = "auto"

_DEFAULT_GEMINI_MODEL = "gemini-2.5-flash-lite"
_DEFAULT_OPENAI_MODEL = "gpt-4o-mini"

# ── Clientes singleton ───────────────────────────────────────────────────────

_openai_client = None
_gemini_client = None


def _get_openai_client():
    global _openai_client
    if _openai_client is None:
        from openai import AsyncOpenAI
        _openai_client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    return _openai_client


def _get_gemini_client():
    global _gemini_client
    if _gemini_client is None:
        from google import genai
        _gemini_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    return _gemini_client


# ── Helpers públicos ──────────────────────────────────────────────────────────

def get_provider() -> str:
    """Devuelve el proveedor configurado (openai | gemini | auto)."""
    return os.getenv("AI_PROVIDER", PROVIDER_OPENAI).strip().lower()


def has_any_provider() -> bool:
    """True si al menos uno de los dos API-keys está configurado."""
    return bool(os.getenv("OPENAI_API_KEY")) or bool(os.getenv("GEMINI_API_KEY"))


def get_default_model(provider: str | None = None) -> str:
    """Devuelve el modelo por defecto según el proveedor."""
    p = provider or get_provider()
    if p == PROVIDER_GEMINI:
        return os.getenv("OPENAI_MODEL", _DEFAULT_GEMINI_MODEL)
    return os.getenv("OPENAI_MODEL", _DEFAULT_OPENAI_MODEL)


def provider_info() -> dict[str, Any]:
    """Información de diagnóstico para logs de startup."""
    prov = get_provider()
    return {
        "provider": prov,
        "openai_key_set": bool(os.getenv("OPENAI_API_KEY")),
        "gemini_key_set": bool(os.getenv("GEMINI_API_KEY")),
    }


# ── Llamadas por proveedor ───────────────────────────────────────────────────

async def _call_openai(
    messages: list[dict],
    model: str | None,
    max_tokens: int,
    temperature: float,
    json_mode: bool,
) -> str:
    client = _get_openai_client()
    resolved_model = model or os.getenv("OPENAI_MODEL", _DEFAULT_OPENAI_MODEL)
    logger.info("OpenAI call — model=%s", resolved_model)

    kwargs: dict[str, Any] = {
        "model": resolved_model,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": messages,
    }
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}

    response = await client.chat.completions.create(**kwargs)
    return response.choices[0].message.content or "{}"


async def _call_gemini(
    messages: list[dict],
    model: str | None,
    max_tokens: int,
    temperature: float,
    json_mode: bool,
) -> str:
    from google.genai import types

    client = _get_gemini_client()
    resolved_model = model or os.getenv("GEMINI_MODEL", _DEFAULT_GEMINI_MODEL)
    logger.info("Gemini call — model=%s", resolved_model)

    # Separar system instruction del resto de mensajes
    system_parts: list[str] = []
    contents: list[types.Content] = []

    for msg in messages:
        role = msg.get("role", "user")
        text = msg.get("content", "")
        if role == "system":
            system_parts.append(text)
        else:
            contents.append(
                types.Content(
                    role="user" if role == "user" else "model",
                    parts=[types.Part.from_text(text=text)],
                )
            )

    config = types.GenerateContentConfig(
        max_output_tokens=max_tokens,
        temperature=temperature,
    )

    if system_parts:
        config.system_instruction = "\n\n".join(system_parts)

    if json_mode:
        config.response_mime_type = "application/json"

    response = await client.aio.models.generate_content(
        model=resolved_model,
        contents=contents,
        config=config,
    )

    return response.text or "{}"


# ── API pública ───────────────────────────────────────────────────────────────

async def chat_completion(
    messages: list[dict],
    *,
    model: str | None = None,
    max_tokens: int = 256,
    temperature: float = 0.1,
    json_mode: bool = False,
) -> str:
    """
    Punto de entrada principal. Envía un chat completion al proveedor configurado.

    Retorna el contenido crudo del mensaje (string).
    En modo ``auto``, intenta el proveedor que tenga API key; si falla, prueba el otro.
    """
    provider = get_provider()

    if provider == PROVIDER_OPENAI:
        return await _call_openai(messages, model, max_tokens, temperature, json_mode)

    if provider == PROVIDER_GEMINI:
        return await _call_gemini(messages, model, max_tokens, temperature, json_mode)

    # ── auto: determinar orden de prioridad ──────────────────────────────
    has_openai = bool(os.getenv("OPENAI_API_KEY"))
    has_gemini = bool(os.getenv("GEMINI_API_KEY"))

    # Gemini primero, OpenAI como fallback
    primary: list[tuple[str, Any]] = []
    if has_gemini:
        primary.append(("gemini", _call_gemini))
    if has_openai:
        primary.append(("openai", _call_openai))

    # El primero disponible es el primario, el segundo el fallback
    attempts = primary if primary else []

    last_exc: Exception | None = None
    for i, (name, call_fn) in enumerate(attempts):
        try:
            # En fallback (i > 0), pasar model=None para que el proveedor
            # resuelva su propio modelo por defecto (no reusar el de otro proveedor)
            effective_model = model if i == 0 else None
            result = await call_fn(messages, effective_model, max_tokens, temperature, json_mode)
            return result
        except Exception as exc:
            logger.warning("Provider '%s' failed (%s), trying next...", name, exc)
            last_exc = exc

    if last_exc:
        raise last_exc
    raise RuntimeError("No AI provider configured. Set OPENAI_API_KEY or GEMINI_API_KEY.")
