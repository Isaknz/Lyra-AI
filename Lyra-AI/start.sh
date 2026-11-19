#!/usr/bin/env bash
# Arranca Ollama (si no está corriendo) y el servidor web del personaje.
set -u

PORT="${PORT:-12000}"
cd "$(dirname "$0")"

if ! curl -s -m 2 http://127.0.0.1:11434/api/version > /dev/null; then
  echo "Iniciando Ollama…"
  mkdir -p .runtime
  nohup ollama serve > .runtime/ollama.log 2>&1 &
  for _ in $(seq 1 30); do
    curl -s -m 1 http://127.0.0.1:11434/api/version > /dev/null && break
    sleep 1
  done
fi

MODEL="${OH_CHARACTER_MODEL:-qwen2.5:3b}"
if ! ollama list 2>/dev/null | awk '{print $1}' | grep -q "^${MODEL%:*}"; then
  echo "Descargando modelo $MODEL…"
  ollama pull "$MODEL"
fi

echo "Chat disponible en http://localhost:$PORT"
echo "La voz se descarga sola la primera vez que la uses (unos 60 MB)."
exec python -m uvicorn app.server:app --host 0.0.0.0 --port "$PORT"
