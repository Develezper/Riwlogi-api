import json
import logging
import os
from openai import AsyncOpenAI

from models import ClassifyRequest, ClassifyResponse, EventSummary

logger = logging.getLogger(__name__)

_client: AsyncOpenAI | None = None


def get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    return _client


# ── Local heuristic (fallback if OpenAI fails) ──────────────────────────────

def classify_heuristic(summary: EventSummary) -> ClassifyResponse:
    total_input = summary.key + summary.paste
    paste_ratio = summary.paste / total_input if total_input > 0 else 0.0

    if paste_ratio >= 0.70:
        label = "ai_generated"
    elif paste_ratio >= 0.35:
        label = "assisted"
    else:
        label = "human"

    confidence = 0.55 + paste_ratio * 0.40
    if summary.run >= 3 and paste_ratio < 0.20:
        confidence -= 0.08

    confidence = round(max(0.50, min(0.98, confidence)), 2)
    return ClassifyResponse(label=label, confidence=confidence)


# ── OpenAI Classifier ────────────────────────────────────────────────────────

SYSTEM_PROMPT = """Eres un clasificador de comportamiento de programación.
Tu tarea es analizar los eventos de interacción de un usuario mientras escribe código
y determinar si el código fue escrito por un humano, generado por IA o asistido por IA.

Criterios de clasificación:
- "human": El usuario escribió el código manualmente (alto ratio key vs paste, ediciones frecuentes, múltiples ejecuciones).
- "assisted": Mezcla de escritura manual y pegado, sugiere uso moderado de herramientas IA o autocompletado.
- "ai_generated": La mayor parte del código fue pegado en uno o pocos bloques grandes (paste_ratio >= 0.7).

Señales clave:
- paste_ratio alto (paste / (key + paste)) → mayor probabilidad de IA.
- Muchos eventos "run" con bajo paste_ratio → comportamiento humano iterativo.
- Muy pocos eventos "key" y muchos "paste" → fuerte indicador de generación IA.

Responde ÚNICAMENTE con un objeto JSON válido con esta estructura exacta:
{"label": "human" | "ai_generated" | "assisted", "confidence": <float entre 0.0 y 1.0>}

No incluyas explicaciones, markdown ni texto adicional."""


async def classify_with_openai(request: ClassifyRequest) -> ClassifyResponse:
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    # Take the last 50 most relevant events (key, paste, delete)
    relevant_events = [
        e for e in request.events
        if e.type in ("key", "paste", "delete", "run")
    ][-50:]

    events_payload = [
        {"type": e.type, "char_count": e.char_count}
        for e in relevant_events
    ]

    summary = request.summary
    total_input = summary.key + summary.paste
    paste_ratio = round(summary.paste / total_input, 3) if total_input > 0 else 0.0

    user_message = f"""Analiza estos datos de comportamiento de programación:

RESUMEN DE EVENTOS:
- Teclas escritas (key): {summary.key} caracteres
- Texto pegado (paste): {summary.paste} caracteres
- Texto eliminado (delete): {summary.delete} caracteres
- Ejecuciones de código (run): {summary.run} veces
- Paste ratio calculado: {paste_ratio} ({paste_ratio * 100:.1f}% del input fue pegado)
- Total eventos analizados: {len(relevant_events)}

ÚLTIMOS EVENTOS (tipo + chars):
{json.dumps(events_payload, ensure_ascii=False)}

Clasifica el comportamiento del programador."""

    try:
        client = get_client()
        response = await client.chat.completions.create(
            model=model,
            max_tokens=60,
            temperature=0.1,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
        )

        raw = response.choices[0].message.content or "{}"
        data = json.loads(raw)

        label = data.get("label", "").strip()
        if label not in ("human", "ai_generated", "assisted"):
            label = classify_heuristic(summary).label

        confidence_raw = data.get("confidence", None)
        confidence = float(confidence_raw) if confidence_raw is not None else classify_heuristic(summary).confidence
        confidence = round(max(0.0, min(1.0, confidence)), 2)

        logger.info("OpenAI classify OK — label=%s confidence=%s paste_ratio=%s", label, confidence, paste_ratio)
        return ClassifyResponse(label=label, confidence=confidence)

    except Exception as exc:
        logger.warning("OpenAI classify failed (%s), using heuristic fallback.", exc)
        return classify_heuristic(summary)


async def classify(request: ClassifyRequest) -> ClassifyResponse:
    """Punto de entrada principal. Siempre devuelve un resultado válido."""
    if not os.getenv("OPENAI_API_KEY"):
        logger.warning("OPENAI_API_KEY not set — using heuristic fallback.")
        return classify_heuristic(request.summary)

    return await classify_with_openai(request)