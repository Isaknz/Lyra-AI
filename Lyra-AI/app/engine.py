"""Motor de chat: habla con Ollama en local, usa herramientas y mantiene historial."""

from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator
from dataclasses import dataclass

import httpx

from . import memoria, tools
from .character import Character

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")
MODEL = os.getenv("OH_CHARACTER_MODEL", "qwen2.5:3b")
TEMPERATURE = float(os.getenv("OH_CHARACTER_TEMPERATURE", "0.8"))
MAX_HISTORY_MESSAGES = int(os.getenv("OH_CHARACTER_HISTORY", "16"))
TOOLS_ENABLED = os.getenv("OH_CHARACTER_TOOLS", "1") not in {"0", "false", "no"}
MAX_TOOL_ROUNDS = 3


@dataclass
class Event:
    """Evento hacia la interfaz: texto del modelo o aviso de herramienta."""

    type: str  # "delta" | "tool"
    text: str = ""


class ChatEngine:
    """Construye el contexto (personaje + memoria + historial) y consulta el modelo."""

    def __init__(self, character: Character) -> None:
        self.character = character
        self.history: list[dict] = []
        self._last_message: dict = {}

    def build_messages(self, user_message: str) -> list[dict]:
        system_text = self.character.system_prompt(memoria.all_facts())
        # La fecha va siempre en el prompt: los modelos pequeños inventan la
        # fecha en vez de llamar a la herramienta, y una fecha falsa es peor
        # que ninguna.
        system_text += f"\n\n## Fecha actual\n{tools.fecha_y_hora()}"

        archivo = tools._menciona_archivo(user_message)
        if archivo:
            # El contenido se entrega ya leído: con 3B el bucle de herramientas
            # acaba pidiendo el nombre del archivo en vez de leerlo.
            contenido = tools.leer_archivo(archivo)
            system_text += (
                f"\n\n## Archivo que el usuario menciona: {archivo}\n"
                "Ya lo has leído. Responde con su contenido sin volver a pedirlo.\n\n"
                f"{contenido}"
            )

        if TOOLS_ENABLED:
            files = tools.listar_archivos()
            system_text += (
                "\n\n## Herramientas\n"
                "Tienes herramientas para leer archivos del usuario, buscar en Wikipedia y "
                "consultar la fecha. Úsalas cuando la pregunta dependa de un dato que no "
                "conoces, en vez de inventarlo.\n"
                "Actúa en vez de pedir permiso: si el usuario pide leer, resumir o "
                "analizar un archivo, llama a leer_archivo y entrega el resultado en el "
                "mismo turno. No preguntes si puedes leerlo ni pidas el nombre: ya te lo "
                "ha pedido y lo tienes abajo.\n"
                "Si una herramienta falla, dilo con naturalidad; no finjas haber leído "
                "algo que no leíste. Cíñete a lo que devuelve la herramienta: no añadas "
                "datos que no aparezcan en el resultado.\n\n"
                "### Archivos disponibles ahora mismo\n"
                f"{files}"
            )
        system = {"role": "system", "content": system_text}
        recent = self.history[-MAX_HISTORY_MESSAGES:]
        return [
            system,
            *self.character.few_shot_messages(),
            *recent,
            {"role": "user", "content": user_message},
        ]

    async def _stream_once(
        self, messages: list[dict], client: httpx.AsyncClient, use_tools: bool = True
    ) -> AsyncIterator[Event]:
        payload: dict = {
            "model": MODEL,
            "messages": messages,
            "stream": True,
            "options": {"temperature": TEMPERATURE, "num_ctx": 4096},
        }
        if TOOLS_ENABLED and use_tools:
            payload["tools"] = tools.TOOL_SCHEMAS

        content: list[str] = []
        calls: list[dict] = []

        async with client.stream("POST", f"{OLLAMA_URL}/api/chat", json=payload) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line.strip():
                    continue
                data = json.loads(line)
                message = data.get("message") or {}
                piece = message.get("content", "")
                if piece:
                    content.append(piece)
                    yield Event("delta", piece)
                calls.extend(message.get("tool_calls") or [])
                if data.get("done"):
                    break

        self._last_message = {"role": "assistant", "content": "".join(content)}
        if calls:
            self._last_message["tool_calls"] = calls
            if content:
                # El modelo escribió un preámbulo antes de decidir usar la herramienta
                # ("¿quieres que lo lea?"). Se descarta para no ensuciar la respuesta.
                yield Event("reset")

    async def stream_reply(self, user_message: str) -> AsyncIterator[Event]:
        messages = self.build_messages(user_message)
        self.history.append({"role": "user", "content": user_message})

        async with httpx.AsyncClient(timeout=httpx.Timeout(300.0, connect=10.0)) as client:
            for _ in range(MAX_TOOL_ROUNDS):
                async for event in self._stream_once(messages, client):
                    yield event

                calls = self._last_message.get("tool_calls") or []
                if not calls:
                    if not self._last_message.get("content"):
                        # Ollama devuelve de vez en cuando una respuesta vacía.
                        # Un reintento sin herramientas suele resolverlo.
                        async for event in self._stream_once(messages, client, use_tools=False):
                            yield event
                    self.history.append(self._last_message)
                    if not self._last_message.get("content"):
                        fallback = "Me he quedado en blanco un momento. ¿Me lo repites?"
                        self._last_message = {"role": "assistant", "content": fallback}
                        yield Event("delta", fallback)
                    return

                messages.append(self._last_message)
                for call in calls:
                    function = call.get("function") or {}
                    name = function.get("name", "")
                    args = function.get("arguments") or {}
                    if isinstance(args, str):
                        try:
                            args = json.loads(args)
                        except json.JSONDecodeError:
                            args = {}
                    result, summary = await tools.run_tool(name, args)
                    yield Event("tool", summary)
                    messages.append({"role": "tool", "content": result, "tool_name": name})

            # Rondas agotadas: pedir una respuesta final sin herramientas.
            async for event in self._stream_once(messages, client, use_tools=False):
                yield event
            self.history.append(self._last_message)

    def reset(self) -> None:
        self.history.clear()


async def check_model() -> tuple[bool, str]:
    """Comprueba que Ollama responde y que el modelo está descargado."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{OLLAMA_URL}/api/tags")
            response.raise_for_status()
            names = {m.get("name", "") for m in response.json().get("models", [])}
    except Exception as exc:  # noqa: BLE001
        return False, f"No se pudo conectar con Ollama en {OLLAMA_URL}: {exc}"
    if not any(name == MODEL or name.startswith(f"{MODEL.split(':')[0]}") for name in names):
        return False, f"El modelo {MODEL} no está descargado. Ejecuta: ollama pull {MODEL}"
    return True, "ok"
