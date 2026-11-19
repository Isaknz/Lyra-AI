"""Memoria persistente: hechos que el personaje recuerda del usuario.

Se guarda como una lista de frases cortas en data/memory.json. Los hechos se
añaden de forma explícita (interfaz o /recuerda en la CLI), nunca los inventa
el modelo, para evitar recuerdos falsos.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

MEMORY_FILE = Path(__file__).resolve().parent.parent / "data" / "memory.json"
MAX_FACTS = 40

_lock = threading.Lock()


def _read() -> list[str]:
    if not MEMORY_FILE.exists():
        return []
    try:
        data = json.loads(MEMORY_FILE.read_text(encoding="utf-8"))
        return [str(item) for item in data] if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def _write(facts: list[str]) -> None:
    MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    MEMORY_FILE.write_text(
        json.dumps(facts, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def all_facts() -> list[str]:
    with _lock:
        return _read()


def remember(fact: str) -> list[str]:
    fact = fact.strip()
    if not fact:
        return all_facts()
    with _lock:
        facts = _read()
        if fact not in facts:
            facts.append(fact)
            _write(facts[-MAX_FACTS:])
        return facts


def forget(fact: str) -> list[str]:
    with _lock:
        facts = [f for f in _read() if f != fact.strip()]
        _write(facts)
        return facts


def clear() -> None:
    with _lock:
        _write([])
