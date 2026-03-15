import json
import logging
import os
import re

from ai_provider import chat_completion, has_any_provider
from models import GenerateProblemRequest, GenerateProblemResponse

logger = logging.getLogger(__name__)

DEFAULT_STARTER_CODE = {
    "python": "def solve(data):\n    # Write your solution here\n    pass",
    "javascript": "function solve(data) {\n  // Write your solution here\n}",
    "typescript": "function solve(data: string): string {\n  // Write your solution here\n}",
}

DEFAULT_STAGE_PROMPT = "Implementa la solucion completa."


SYSTEM_PROMPT = """Eres un generador experto de ejercicios de programación para una plataforma tipo coding challenge.

Tu tarea es crear un ejercicio completo, claro, resoluble y editable por un humano.
Debes responder SOLO con un único objeto JSON válido.
No uses markdown fuera de los strings del JSON.
No agregues explicaciones, comentarios, texto antes o después, ni bloques de código.

La salida debe seguir EXACTAMENTE esta estructura:
{
  "title": "string",
  "difficulty": 1,
  "tags": ["string"],
  "statement_md": "string en markdown",
  "starter_code": {
    "python": "string",
    "javascript": "string",
    "typescript": "string"
  },
  "stages": [
    {
      "stage_index": 1,
      "prompt_md": "string markdown",
      "hidden_count": 1,
      "visible_tests": [
        { "input_text": "string", "expected_text": "string" }
      ],
      "hidden_tests": [
        { "input_text": "string", "expected_text": "string" }
      ]
    }
  ]
}

Objetivo del ejercicio:
- Debe ser un problema clásico de programación, claro y autocontenido.
- Debe poder resolverse implementando una función solve.
- Debe usar solo entrada y salida en texto.
- Debe ser determinista, sin aleatoriedad, sin fecha/hora actual, sin red, sin archivos y sin librerías externas.
- Debe quedar listo para que luego un humano lo edite manualmente.

Reglas obligatorias:
1) "stages" debe ser un arreglo con exactamente 1 elemento.
2) La única etapa debe incluir SIEMPRE: stage_index, prompt_md, hidden_count, visible_tests, hidden_tests.
3) "stage_index" debe ser exactamente 1.
4) "visible_tests" debe tener al menos 1 caso.
5) "hidden_tests" debe tener al menos 1 caso.
6) "hidden_count" debe ser exactamente igual a la cantidad real de elementos en "hidden_tests".
7) "starter_code" debe incluir obligatoriamente "python", "javascript" y "typescript".
8) En los tres lenguajes debe existir una función llamada solve.
9) "difficulty" solo puede ser 1, 2 o 3.
10) No agregues claves extra fuera de la estructura definida.
11) Todos los strings deben ser válidos en JSON y estar correctamente escapados.
12) El ejercicio no debe depender de conocimiento externo, contexto previo ni interpretación subjetiva.
13) El enunciado, los tests y el starter code deben ser consistentes entre sí.
14) Los tests visibles no deben contradecir los ocultos.
15) Los tests ocultos deben cubrir edge cases o casos límite reales.

Criterios de calidad del ejercicio:
- El título debe ser corto, claro y específico.
- Los tags deben ser útiles, en minúsculas, sin duplicados, entre 2 y 5 elementos.
- La dificultad debe corresponder con la complejidad real del problema.
- El problema debe ser resoluble en una sola función.
- Evita problemas interactivos.
- Evita problemas excesivamente largos o con reglas ambiguas.
- Evita ejercicios triviales sin validación interesante.
- Evita ejercicios imposibles de verificar solo con input_text y expected_text.

Formato requerido para "statement_md":
Incluye estas secciones en este orden:
1. ## Descripción
2. ## Entrada
3. ## Salida
4. ## Restricciones
5. ## Ejemplos

Formato requerido para "prompt_md":
- Debe ser una versión breve y operativa de la tarea.
- Debe indicar claramente qué debe implementar el usuario.
- Debe mencionar qué representa el input y qué debe devolver.

Reglas para "starter_code":
- Debe ser mínimo, limpio y editable.
- No incluyas solución completa.
- No incluyas lógica del algoritmo resuelto.
- Solo define la función solve con una estructura base simple.
- La función debe recibir un string y devolver un string.
- Usa exactamente estas firmas conceptuales, OBLIGANDO a incluir el parámetro `input_text` en la firma:
  - Python: def solve(input_text: str) -> str:
  - JavaScript: function solve(input_text) { ... }
  - TypeScript: function solve(input_text: string): string { ... }
  - NUNCA omitas el parámetro `input_text` en la definición de la función.

Reglas para tests:
- Cada "input_text" debe representar exactamente la entrada cruda del problema.
- Cada "expected_text" debe representar exactamente la salida esperada.
- Usa casos pequeños pero representativos.
- Los visibles deben ayudar a entender el problema.
- Los ocultos deben cubrir al menos uno de estos: mínimo, máximo razonable, borde, repetidos, vacíos si aplica, formato sensible, empate si aplica.
- No generes tests redundantes.

Guía de dificultad:
- 1 = fácil: lógica directa, pocas reglas, implementación corta.
- 2 = intermedio: varios pasos, parsing moderado, algo de manejo de casos borde.
- 3 = difícil: lógica más elaborada, varios casos, mayor cuidado algorítmico.

Antes de responder, valida internamente todo esto:
- El JSON es válido.
- La estructura es exacta.
- hidden_count coincide con hidden_tests.length.
- Hay exactamente una etapa.
- El problema es claro y resoluble.
- Los tests coinciden con el enunciado.
- El starter_code no contiene la solución.
- La salida final contiene solo JSON válido.

Genera ahora un único ejercicio completo.
"""


def clamp_int(value, default, minimum, maximum):
    try:
        parsed = int(value)
    except Exception:
        return default
    return max(minimum, min(maximum, parsed))


def infer_title(prompt: str) -> str:
    candidate = re.split(r"[.!?\n]", str(prompt or "").strip())[0].strip()
    if not candidate:
        return "AI Generated Problem"
    return candidate[:110]


def normalize_tags(raw_tags) -> list[str]:
    if isinstance(raw_tags, str):
        source = [part.strip() for part in raw_tags.split(",")]
    elif isinstance(raw_tags, list):
        source = [str(item or "").strip() for item in raw_tags]
    else:
        source = []

    tags = []
    seen = set()
    for tag in source:
        if not tag:
            continue
        normalized = tag.lower()
        if normalized in seen:
            continue
        seen.add(normalized)
        tags.append(normalized)
        if len(tags) >= 8:
            break

    return tags if tags else ["ai-generated"]


def normalize_starter_code(raw_starter):
    raw = raw_starter if isinstance(raw_starter, dict) else {}
    python_code = str(raw.get("python") or "").rstrip()
    javascript_code = str(raw.get("javascript") or "").rstrip()
    typescript_code = str(raw.get("typescript") or "").rstrip()

    return {
        "python": python_code or DEFAULT_STARTER_CODE["python"],
        "javascript": javascript_code or DEFAULT_STARTER_CODE["javascript"],
        "typescript": typescript_code or DEFAULT_STARTER_CODE["typescript"],
    }


def normalize_visible_tests(raw_tests):
    tests = []
    if isinstance(raw_tests, list):
        for raw in raw_tests:
            if not isinstance(raw, dict):
                continue
            input_text = str(raw.get("input_text") or "").strip()
            expected_text = str(raw.get("expected_text") or "").strip()
            if not input_text or not expected_text:
                continue
            tests.append(
                {
                    "input_text": input_text[:2000],
                    "expected_text": expected_text[:2000],
                }
            )
            if len(tests) >= 6:
                break

    if not tests:
        raise ValueError("visible_tests must include at least one valid test case")

    return tests


def normalize_hidden_tests(raw_tests):
    tests = []
    if isinstance(raw_tests, list):
        for raw in raw_tests:
            if not isinstance(raw, dict):
                continue
            input_text = str(raw.get("input_text") or "").strip()
            expected_text = str(raw.get("expected_text") or "").strip()
            if not input_text or not expected_text:
                continue
            tests.append(
                {
                    "input_text": input_text[:2000],
                    "expected_text": expected_text[:2000],
                }
            )
            if len(tests) >= 20:
                break
    return tests


def normalize_single_stage(raw_stages):
    source = raw_stages if isinstance(raw_stages, list) else []
    raw_stage = source[0] if source and isinstance(source[0], dict) else {}

    prompt_md = str(raw_stage.get("prompt_md") or "").strip()
    hidden_count = clamp_int(raw_stage.get("hidden_count"), 2, 0, 2000)

    if len(prompt_md) < 3:
        raise ValueError("stage prompt_md is required")

    return [
        {
            "stage_index": 1,
            "prompt_md": prompt_md,
            "hidden_count": hidden_count,
            "visible_tests": normalize_visible_tests(raw_stage.get("visible_tests")),
            "hidden_tests": normalize_hidden_tests(raw_stage.get("hidden_tests")),
        }
    ]


def normalize_generated_payload(raw_data, prompt: str) -> GenerateProblemResponse:
    if not isinstance(raw_data, dict):
        raw_data = {}

    title = str(raw_data.get("title") or "").strip()[:140]
    difficulty = clamp_int(raw_data.get("difficulty"), 2, 1, 3)
    statement_md = str(raw_data.get("statement_md") or "").strip()

    if len(statement_md) < 10:
        raise ValueError("statement_md is missing or too short")

    payload = {
        "title": title or infer_title(prompt),
        "difficulty": difficulty,
        "tags": normalize_tags(raw_data.get("tags")),
        "statement_md": statement_md,
        "starter_code": normalize_starter_code(raw_data.get("starter_code")),
        "stages": normalize_single_stage(raw_data.get("stages")),
    }

    return GenerateProblemResponse.model_validate(payload)


async def generate_problem(request: GenerateProblemRequest) -> GenerateProblemResponse:
    prompt = request.prompt

    if not has_any_provider():
        logger.error("No AI provider configured for problem generation.")
        raise RuntimeError("Problem generation is unavailable because no AI provider is configured")

    model = os.getenv("AI_GENERATION_MODEL", os.getenv("OPENAI_MODEL"))
    user_message = f"""Genera un ejercicio a partir de este prompt del usuario:

PROMPT_USUARIO:
{prompt}

Regla obligatoria: devuelve exactamente una etapa en \"stages\" con stage_index=1."""

    try:
        raw = await chat_completion(
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            model=model,
            max_tokens=2500,
            temperature=0.25,
            json_mode=True,
        )

        parsed = json.loads(raw)
        result = normalize_generated_payload(parsed, prompt)
        logger.info(
            "AI generation OK — title=%s difficulty=%s stages=%s",
            result.title,
            result.difficulty,
            len(result.stages),
        )
        return result
    except Exception as exc:
        logger.error("AI generation failed (%s).", exc)
        raise RuntimeError("Problem generation failed due to upstream AI error") from exc
