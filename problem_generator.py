import json
import logging
import os
import re

from openai import AsyncOpenAI

from models import GenerateProblemRequest, GenerateProblemResponse

logger = logging.getLogger(__name__)

_client: AsyncOpenAI | None = None

DEFAULT_STARTER_CODE = {
    "python": "def solve(data):\n    # Write your solution here\n    pass",
    "javascript": "function solve(data) {\n  // Write your solution here\n}",
}

DEFAULT_STAGE_PROMPT = "Implementa la solucion completa."


SYSTEM_PROMPT = """Eres un generador de ejercicios de programacion para una plataforma tipo coding challenge.
Debes responder SOLO con JSON valido, sin markdown y sin texto extra.

Objetivo:
Crear un ejercicio completo y editable con esta estructura exacta:
{
  "title": "string",
  "difficulty": 1 | 2 | 3,
  "tags": ["string", "..."],
  "statement_md": "string en markdown",
  "starter_code": {
    "python": "string",
    "javascript": "string"
  },
  "stages": [
    {
      "stage_index": 1,
      "prompt_md": "string markdown",
      "hidden_count": 2,
      "visible_tests": [
        { "input_text": "string", "expected_text": "string" }
      ]
    }
  ]
}

Reglas obligatorias:
1) "stages" debe ser una lista con exactamente una etapa.
2) La etapa unica debe incluir SIEMPRE: stage_index, prompt_md, hidden_count, visible_tests.
3) stage_index debe ser 1.
4) visible_tests debe tener minimo 1 caso.
5) starter_code debe incluir python y javascript con funcion solve.
6) difficulty solo puede ser 1 (facil), 2 (intermedio), 3 (dificil).
7) El ejercicio debe quedar listo para que luego un humano lo edite manualmente."""


def get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    return _client


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

    return {
        "python": python_code or DEFAULT_STARTER_CODE["python"],
        "javascript": javascript_code or DEFAULT_STARTER_CODE["javascript"],
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

    if tests:
        return tests

    return [
        {
            "input_text": "example_input_stage_1",
            "expected_text": "example_output_stage_1",
        }
    ]


def normalize_single_stage(raw_stages):
    source = raw_stages if isinstance(raw_stages, list) else []
    raw_stage = source[0] if source and isinstance(source[0], dict) else {}

    prompt_md = str(raw_stage.get("prompt_md") or "").strip()
    hidden_count = clamp_int(raw_stage.get("hidden_count"), 2, 0, 2000)

    return [
        {
            "stage_index": 1,
            "prompt_md": prompt_md or DEFAULT_STAGE_PROMPT,
            "hidden_count": hidden_count,
            "visible_tests": normalize_visible_tests(raw_stage.get("visible_tests")),
        }
    ]


def build_fallback_payload(prompt: str):
    title = infer_title(prompt)
    return {
        "title": title,
        "difficulty": 2,
        "tags": ["ai-generated"],
        "statement_md": f"## Description\n\n{prompt}\n\n## Notes\n\nSolve the problem using the function `solve`.",
        "starter_code": DEFAULT_STARTER_CODE,
        "stages": normalize_single_stage([]),
    }


def normalize_generated_payload(raw_data, prompt: str) -> GenerateProblemResponse:
    if not isinstance(raw_data, dict):
        raw_data = {}

    title = str(raw_data.get("title") or "").strip()[:140]
    difficulty = clamp_int(raw_data.get("difficulty"), 2, 1, 3)
    statement_md = str(raw_data.get("statement_md") or "").strip()
    payload = {
        "title": title or infer_title(prompt),
        "difficulty": difficulty,
        "tags": normalize_tags(raw_data.get("tags")),
        "statement_md": statement_md or build_fallback_payload(prompt)["statement_md"],
        "starter_code": normalize_starter_code(raw_data.get("starter_code")),
        "stages": normalize_single_stage(raw_data.get("stages")),
    }

    try:
        return GenerateProblemResponse.model_validate(payload)
    except Exception as exc:
        logger.warning("Generated payload validation failed (%s), using fallback payload.", exc)
        return GenerateProblemResponse.model_validate(build_fallback_payload(prompt))


async def generate_problem(request: GenerateProblemRequest) -> GenerateProblemResponse:
    prompt = request.prompt

    if not os.getenv("OPENAI_API_KEY"):
        logger.warning("OPENAI_API_KEY not set for problem generation. Using fallback payload.")
        return GenerateProblemResponse.model_validate(build_fallback_payload(prompt))

    model = os.getenv("OPENAI_GENERATION_MODEL", os.getenv("OPENAI_MODEL", "gpt-4o-mini"))
    user_message = f"""Genera un ejercicio a partir de este prompt del usuario:

PROMPT_USUARIO:
{prompt}

Regla obligatoria: devuelve exactamente una etapa en \"stages\" con stage_index=1."""

    try:
        client = get_client()
        response = await client.chat.completions.create(
            model=model,
            temperature=0.25,
            max_tokens=2500,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
        )

        raw = response.choices[0].message.content or "{}"
        parsed = json.loads(raw)
        result = normalize_generated_payload(parsed, prompt)
        logger.info(
            "OpenAI generation OK — title=%s difficulty=%s stages=%s",
            result.title,
            result.difficulty,
            len(result.stages),
        )
        return result
    except Exception as exc:
        logger.warning("OpenAI generation failed (%s), using fallback payload.", exc)
        fallback = build_fallback_payload(prompt)
        return GenerateProblemResponse.model_validate(fallback)
