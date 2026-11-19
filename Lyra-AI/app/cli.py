"""Modo terminal: conversa con el personaje sin abrir el navegador.

Uso:
    python -m app.cli
Comandos: /salir  /nuevo  /recuerda <hecho>  /memoria  /olvida <hecho>  /personaje
"""

from __future__ import annotations

import asyncio
import sys

from . import memoria
from .character import load_character
from .engine import ChatEngine, MODEL, check_model

BOLD = "\033[1m"
DIM = "\033[2m"
ACCENT = "\033[38;5;141m"
RESET = "\033[0m"


async def main() -> None:
    ok, detail = await check_model()
    if not ok:
        print(f"{detail}")
        sys.exit(1)

    character = load_character()
    engine = ChatEngine(character)
    print(f"{ACCENT}{character.avatar} {character.name}{RESET} {DIM}({MODEL}){RESET}")
    if character.tagline:
        print(f"{DIM}{character.tagline}{RESET}")
    print(f"{DIM}/salir /nuevo /recuerda /memoria /olvida /personaje{RESET}\n")

    while True:
        try:
            text = input(f"{BOLD}tú ›{RESET} ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not text:
            continue

        if text.startswith("/"):
            command, _, arg = text[1:].partition(" ")
            if command in {"salir", "exit", "quit"}:
                break
            if command == "nuevo":
                engine.reset()
                print(f"{DIM}Conversación reiniciada.{RESET}\n")
                continue
            if command == "recuerda":
                if not arg.strip():
                    print(f"{DIM}Uso: /recuerda <hecho>{RESET}\n")
                    continue
                memoria.remember(arg)
                print(f"{DIM}Recordado.{RESET}\n")
                continue
            if command == "memoria":
                facts = memoria.all_facts()
                print(f"{DIM}" + ("\n".join(f"  · {f}" for f in facts) or "  (vacía)") + f"{RESET}\n")
                continue
            if command == "olvida":
                memoria.forget(arg)
                print(f"{DIM}Olvidado.{RESET}\n")
                continue
            if command == "personaje":
                print(f"{DIM}{character.system_prompt(memoria.all_facts())}{RESET}\n")
                continue
            print(f"{DIM}Comando desconocido.{RESET}\n")
            continue

        print(f"{ACCENT}{character.name} ›{RESET} ", end="", flush=True)
        try:
            async for event in engine.stream_reply(text):
                if event.type == "delta":
                    print(event.text, end="", flush=True)
                elif event.type == "tool":
                    print(f"{DIM}[{event.text}]{RESET} ", end="", flush=True)
                elif event.type == "reset":
                    print(f"\r\033[K{ACCENT}{character.name} ›{RESET} ", end="", flush=True)
        except Exception as exc:  # noqa: BLE001
            print(f"\n{DIM}Error: {exc}{RESET}", end="")
        print("\n")


if __name__ == "__main__":
    asyncio.run(main())
