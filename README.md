# Riwlogi Classifier API

API FastAPI que clasifica el comportamiento de programación de un usuario
usando OpenAI. Se integra con el backend Node.js de Riwlogi via `CLASSIFIER_API_BASE`.

Este servicio vive en la carpeta `api/` del monorepo (antes `classifier-api`).

## Cómo funciona

Cuando un usuario envía código, el backend Node.js envía los eventos de
interacción (teclas, pegado, borrado, ejecuciones) a esta API. OpenAI analiza
el patrón y devuelve si el código fue escrito por un humano, asistido por IA
o generado por IA.

Si OpenAI no está disponible o falla, la API usa una **heurística local** como
fallback automático, por lo que el backend Node.js nunca se ve afectado.

---

## Instalación y arranque

### Opcion recomendada (un solo comando)

Desde la carpeta `api/`:

```bash
make run
```

o:

```bash
./start.sh
```

Este script:
- Crea `.venv` (si no existe)
- Instala dependencias de `requirements.txt`
- Crea `.env` desde `.env.example` (si no existe)
- Levanta `uvicorn` con `--reload`

### Opcion manual

```bash
# Crear el entorno virtual
python3 -m venv .venv

# Activar el entorno virtual
source .venv/bin/activate

# 1. Instalar dependencias
pip install -r requirements.txt

# 2. Configurar variables de entorno
cp .env.example .env
# Edita .env y agrega tu OPENAI_API_KEY

# 3. Levantar el servidor
uvicorn main:app --host 0.0.0.0 --port 8001 --reload
```

La API estará disponible en: `http://localhost:8001`
Documentación interactiva: `http://localhost:8001/docs`

---

## Configuración en el backend Node.js

Agrega esta variable al `.env` del backend Riwlogi:

```env
CLASSIFIER_API_BASE=http://localhost:8001
```

En producción, apunta a la URL donde esté desplegada esta API:

```env
CLASSIFIER_API_BASE=https://tu-classifier-api.com
```

## Despliegue en Render (Docker)

Este repo incluye `render.yaml` y `Dockerfile` para desplegar con contenedor.
Puntos importantes:
- El servicio en `render.yaml` usa `env: docker` (no runtime Python).
- Render inyecta `PORT` automaticamente.
- El health check usa `GET /health`.

Variable obligatoria en Render:
- `OPENAI_API_KEY`

---

## Endpoints

### `GET /health`
Health check para verificar que la API está activa.

```json
{ "ok": true, "status": "ok" }
```

### `POST /classify`
Clasifica el comportamiento de programación.

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

Valores posibles de `label`:
- `"human"` — código escrito manualmente
- `"assisted"` — uso moderado de herramientas IA / autocompletado
- `"ai_generated"` — código principalmente pegado / generado por IA

### `POST /generate-problem`
Genera un ejercicio completo para el panel admin a partir de un prompt.

**Request:**
```json
{
  "prompt": "Crea un ejercicio sobre reverse string con 3 etapas progresivas."
}
```

**Response (resumen):**
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

## Variables de entorno

| Variable | Default | Descripción |
|---|---|---|
| `OPENAI_API_KEY` | *(requerido)* | API Key de OpenAI |
| `OPENAI_MODEL` | `gpt-4o-mini` | Modelo de OpenAI a usar |
| `OPENAI_GENERATION_MODEL` | `OPENAI_MODEL` | Modelo para el endpoint de generación de ejercicios |
| `HOST` | `0.0.0.0` | Host del servidor |
| `PORT` | `8001` | Puerto del servidor |
| `CORS_ORIGINS` | `*` | Orígenes permitidos (lista separada por comas) |

> Si levantas la API desde el backend Node.js (autostart), puedes controlar el host/puerto
> con `CLASSIFIER_API_HOST` y `CLASSIFIER_API_PORT` en el `.env` del backend.

---

## Estructura del proyecto

```
api/
├── main.py          # App FastAPI, endpoints, lifespan
├── models.py        # Modelos Pydantic (request/response)
├── classifier.py    # Lógica OpenAI + fallback heurístico
├── problem_generator.py # Prompt interno + generación de ejercicios
├── requirements.txt
├── .env.example
└── README.md
```
