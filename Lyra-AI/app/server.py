"""Servidor web: chat con streaming, gestión de personaje y memoria."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import memoria, tts, tools
from .character import list_characters, load_character
from .engine import ChatEngine, MODEL, TOOLS_ENABLED, check_model

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(title="IA local con personaje")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

_character = load_character()
engine = ChatEngine(_character)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)


class MemoryRequest(BaseModel):
    fact: str = Field(min_length=1, max_length=500)


def _character_info() -> dict:
    char = engine.character
    return {
        "name": char.name,
        "role": char.role,
        "avatar": char.avatar,
        "tagline": char.tagline,
        "pronouns": char.pronouns,
        "personality": char.personality,
        "slug": char.slug,
        "model": MODEL,
        "tools": TOOLS_ENABLED,
        "voice": tts.available(),
        "available_characters": list_characters(),
    }


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/character")
async def get_character() -> dict:
    return _character_info()


@app.get("/api/health")
async def health() -> dict:
    ok, detail = await check_model()
    return {"ok": ok, "detail": detail, "model": MODEL}


@app.post("/api/chat")
async def chat(request: ChatRequest) -> StreamingResponse:
    async def event_stream():
        yield f"data: {json.dumps({'type': 'start'})}\n\n"
        try:
            async for event in engine.stream_reply(request.message):
                yield f"data: {json.dumps({'type': event.type, 'text': event.text})}\n\n"
        except Exception as exc:  # noqa: BLE001
            yield f"data: {json.dumps({'type': 'error', 'text': str(exc)})}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


class TTSRequest(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


@app.post("/api/tts")
async def synthesize(request: TTSRequest) -> Response:
    if not tts.available():
        raise HTTPException(
            status_code=503, detail="La voz no está instalada (pip install piper-tts)."
        )
    try:
        audio = await run_in_threadpool(tts.synthesize, request.text)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Error de voz: {exc}") from exc
    return Response(
        content=audio,
        media_type="audio/wav",
        headers={"Cache-Control": "no-store"},
    )


@app.get("/api/tools")
async def get_tools() -> dict:
    return {
        "enabled": TOOLS_ENABLED,
        "root": str(tools.TOOL_ROOT),
        "tools": [schema["function"]["name"] for schema in tools.TOOL_SCHEMAS],
        "files": tools.listar_archivos(),
    }


@app.post("/api/reset")
async def reset() -> dict:
    engine.reset()
    return {"ok": True}


@app.get("/api/memory")
async def get_memory() -> dict:
    return {"facts": memoria.all_facts()}


@app.post("/api/memory")
async def add_memory(request: MemoryRequest) -> dict:
    return {"facts": memoria.remember(request.fact)}


@app.delete("/api/memory")
async def delete_memory(fact: str) -> dict:
    return {"facts": memoria.forget(fact)}


@app.post("/api/memory/clear")
async def clear_memory() -> dict:
    memoria.clear()
    return {"facts": []}


@app.post("/api/character/reload")
async def reload_character(name: str | None = None) -> dict:
    global _character
    try:
        _character = load_character(f"characters/{name}.yaml" if name else None)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    engine.character = _character
    engine.reset()
    return _character_info()
