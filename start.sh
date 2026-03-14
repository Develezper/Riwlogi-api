#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$ROOT_DIR/.venv"
PYTHON_BIN="${PYTHON_BIN:-python3}"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "Error: no se encontro '$PYTHON_BIN' en el PATH."
  exit 1
fi

cd "$ROOT_DIR"

if [[ ! -d "$VENV_DIR" ]]; then
  echo "[setup] Creando entorno virtual en .venv"
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

echo "[setup] Instalando dependencias"
pip install --upgrade pip >/dev/null
pip install -r requirements.txt

if [[ ! -f .env && -f .env.example ]]; then
  cp .env.example .env
  echo "[setup] Se creo .env desde .env.example"
fi

HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8001}"

echo "[run] Iniciando API en http://$HOST:$PORT"
exec uvicorn main:app --host "$HOST" --port "$PORT" --reload
