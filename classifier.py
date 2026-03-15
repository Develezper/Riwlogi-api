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


# ── Heurística local (fallback si OpenAI falla) ─────────────────────────────

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
    if summary.focus >= 5 and paste_ratio >= 0.35:
        confidence += 0.05

    confidence = round(max(0.50, min(0.98, confidence)), 2)
    return ClassifyResponse(label=label, confidence=confidence)


# ── Clasificador con OpenAI ──────────────────────────────────────────────────

SYSTEM_PROMPT = """Eres un sistema experto en análisis de biometría de teclado y estilometría de código.
Tu tarea es analizar métricas de interacción del usuario y código fuente para clasificar su autoría.

<criterios_de_clasificacion>
1. "human":
   - Comportamiento: Ratio de pegado muy bajo (paste_ratio < 0.2). Múltiples ejecuciones iterativas (`run`). Presencia notable de ediciones, borrados e iteraciones de prueba y error. Cambios de foco (`focus`) ocasionales y consistentes con consultar documentación.
   - Código: Nombres de variables simples, abreviados o coloquiales. Comentarios escasos o enfocados en el "por qué". Posibles inconsistencias de estilo, refactorizaciones a medias o errores lógicos menores. Estructura orgánica.

2. "assisted":
   - Comportamiento: Mezcla de tipado sostenido con inserciones de texto de tamaño mediano (paste_ratio entre 0.2 y 0.6). Sugiere el uso de autocompletado avanzado (ej. GitHub Copilot). Cambios de foco moderados.
   - Código: Lógica principal y estructura escrita a mano, combinada con bloques altamente estructurados (ej. regex complejos, docstrings autogenerados, o boilerplate perfecto).

3. "ai_generated":
   - Comportamiento: La gran mayoría del código ingresó en bloque (paste_ratio >= 0.7). Ausencia de desarrollo iterativo (muy pocos eventos `key`, escasos eventos `run` intermedios). Muchos cambios de foco (`focus`) seguidos de pastes grandes sugieren copiar desde una herramienta de IA externa.
   - Código: Estructura de "libro de texto". Comentarios excesivos o redundantes que explican líneas de código obvias. Variables excesivamente descriptivas (ej. `filtered_valid_user_data_list`). Manejo exhaustivo de edge cases en scripts que deberían ser simples.
</criterios_de_clasificacion>

<instrucciones_estrictas>
1. Evalúa PRIMERO las señales de comportamiento, son el indicador más fuerte.
2. Evalúa SEGUNDO las características del código para confirmar la hipótesis.
3. Responde ÚNICAMENTE con un objeto JSON válido.
4. NO uses bloques de código de markdown (no uses ```json ni ```). Devuelve directamente el texto con las llaves {}.
</instrucciones_estrictas>

<formato_de_salida>
{
  "label": "human" | "assisted" | "ai_generated",
  "confidence": <float entre 0.0 y 1.0>
}
</formato_de_salida>
"""


async def classify_with_openai(request: ClassifyRequest) -> ClassifyResponse:
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    # Tomar los últimos 50 eventos más relevantes (key, paste, delete)
    relevant_events = [
        e for e in request.events
        if e.type in ("key", "paste", "delete", "run", "focus")
    ][-50:]

    events_payload = [
        {"type": e.type, "char_count": e.char_count}
        for e in relevant_events
    ]

    summary = request.summary
    total_input = summary.key + summary.paste
    paste_ratio = round(summary.paste / total_input, 3) if total_input > 0 else 0.0

    code_section = ""
    if request.code and request.code.strip():
        truncated_code = request.code.strip()[:4000]
        code_section = f"""

<datos_de_entrada>
CÓDIGO ENVIADO POR EL USUARIO:
```
{truncated_code}
```"""

    user_message = f"""Analiza estos datos de comportamiento de programación:

RESUMEN DE EVENTOS:
- Teclas escritas (key): {summary.key} caracteres
- Texto pegado (paste): {summary.paste} caracteres
- Texto eliminado (delete): {summary.delete} caracteres
- Ejecuciones de código (run): {summary.run} veces
- Cambios de foco (focus): {summary.focus} veces
- Paste ratio calculado: {paste_ratio} ({paste_ratio * 100:.1f}% del input fue pegado)
- Total eventos analizados: {len(relevant_events)}

ÚLTIMOS EVENTOS (tipo + chars):
{json.dumps(events_payload, ensure_ascii=False)}{code_section}

</datos_de_entrada>

Clasifica el comportamiento del programador considerando tanto los eventos de interacción como el estilo del código."""

    try:
        client = get_client()
        response = await client.chat.completions.create(
            model=model,
            max_tokens=100,
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