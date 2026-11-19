"""Carga de la ficha de personaje y construcción del prompt de sistema."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

CHARACTERS_DIR = Path(__file__).resolve().parent.parent / "characters"
DEFAULT_CHARACTER = os.getenv("OH_CHARACTER", "lyra")


@dataclass
class Example:
    user: str
    assistant: str


@dataclass
class Character:
    name: str
    role: str = "asistente"
    pronouns: str = "neutral"
    avatar: str = "🤖"
    tagline: str = ""
    voice: str = ""
    personality: list[str] = field(default_factory=list)
    backstory: str = ""
    rules: list[str] = field(default_factory=list)
    boundaries: list[str] = field(default_factory=list)
    examples: list[Example] = field(default_factory=list)
    slug: str = "character"

    def system_prompt(self, memories: list[str] | None = None) -> str:
        lines = [
            f"Te llamas {self.name}. Eres {self.role}.",
            f"Tu pronombre es {self.pronouns}.",
        ]
        if self.backstory:
            lines += ["", "## Tu historia", self.backstory.strip()]
        if self.voice:
            lines += ["", "## Cómo hablas", self.voice.strip()]
        if self.personality:
            lines += ["", "## Tu personalidad"]
            lines += [f"- {item}" for item in self.personality]
        if self.rules:
            lines += ["", "## Reglas que siempre cumples"]
            lines += [f"- {item}" for item in self.rules]
        if self.boundaries:
            lines += ["", "## Límites"]
            lines += [f"- {item}" for item in self.boundaries]
        if memories:
            lines += ["", "## Lo que recuerdas del usuario"]
            lines += [f"- {item}" for item in memories]
        lines += [
            "",
            f"Habla siempre en primera persona como {self.name}, "
            "sin narrar acciones entre asteriscos salvo que el usuario lo pida.",
        ]
        return "\n".join(lines)

    def few_shot_messages(self) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = []
        for example in self.examples:
            messages.append({"role": "user", "content": example.user})
            messages.append({"role": "assistant", "content": example.assistant})
        return messages


def load_character(path: str | Path | None = None) -> Character:
    file_path = Path(path) if path else CHARACTERS_DIR / f"{DEFAULT_CHARACTER}.yaml"
    if not file_path.exists():
        raise FileNotFoundError(f"No se encontró la ficha de personaje: {file_path}")

    raw = yaml.safe_load(file_path.read_text(encoding="utf-8")) or {}

    voice = raw.get("voice") or {}
    voice_text = voice.get("description", "") if isinstance(voice, dict) else str(voice)

    examples = [
        Example(user=str(item.get("user", "")), assistant=str(item.get("assistant", "")))
        for item in (raw.get("examples") or [])
        if isinstance(item, dict)
    ]

    return Character(
        name=raw.get("name", "Asistente"),
        role=raw.get("role", "asistente"),
        pronouns=raw.get("pronouns", "neutral"),
        avatar=raw.get("avatar", "🤖"),
        tagline=raw.get("tagline", ""),
        voice=voice_text,
        personality=list(raw.get("personality") or []),
        backstory=raw.get("backstory", ""),
        rules=list(raw.get("rules") or []),
        boundaries=list(raw.get("boundaries") or []),
        examples=examples,
        slug=file_path.stem,
    )


def list_characters() -> list[str]:
    return sorted(p.stem for p in CHARACTERS_DIR.glob("*.yaml") if not p.stem.startswith("_"))
