"""Herramientas del personaje: archivos locales y búsqueda web.

Todo está limitado a propósito: los archivos solo se leen dentro de
``workspace/`` y la búsqueda usa la API pública de Wikipedia (sin clave).
Así el modelo no puede tocar nada fuera de su caja.
"""

from __future__ import annotations

import difflib
import os
import re
from datetime import datetime
from pathlib import Path

import httpx

TOOL_ROOT = Path(os.getenv("OH_TOOL_ROOT", "workspace")).resolve()
MAX_FILE_BYTES = 40_000
MAX_RESULTS = 4

WIKI_UA = "LyraAI/1.0 (asistente local; uso personal)"


TOOL_SCHEMAS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "listar_archivos",
            "description": (
                "Lista los archivos disponibles en el espacio de trabajo del usuario. "
                "Úsalo cuando el usuario pregunte qué documentos tiene o pida trabajar con uno."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "leer_archivo",
            "description": (
                "Lee el contenido de un archivo de texto del espacio de trabajo. "
                "Úsalo cuando el usuario pida resumir, analizar o buscar algo en un documento."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "nombre": {
                        "type": "string",
                        "description": "Nombre del archivo, por ejemplo 'notas.txt'.",
                    }
                },
                "required": ["nombre"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "buscar_en_wikipedia",
            "description": (
                "Busca información factual y actualizada en Wikipedia. "
                "Úsalo para datos concretos, personas, lugares o hechos que no conozcas con seguridad."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "consulta": {"type": "string", "description": "Término a buscar."}
                },
                "required": ["consulta"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fecha_y_hora",
            "description": "Devuelve la fecha y hora actuales del equipo del usuario.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]


def _safe_path(nombre: str) -> Path:
    candidate = (TOOL_ROOT / nombre).resolve()
    if not candidate.is_relative_to(TOOL_ROOT):
        raise ValueError("Ese archivo está fuera del espacio de trabajo permitido.")
    return candidate


def _normalize(name: str) -> str:
    """Minúsculas y sin acentos, para comparar nombres de archivo."""
    import unicodedata

    decomposed = unicodedata.normalize("NFKD", name.lower())
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def _resolve(nombre: str) -> Path | None:
    """Busca el archivo tolerando mayúsculas, acentos y nombres aproximados.

    Los modelos pequeños inventan a menudo el nombre del archivo (traducen
    'ejemplo-notas.txt' a 'example-notes.txt'), así que conviene ser flexible.
    """
    try:
        exact = _safe_path(nombre)
        if exact.is_file():
            return exact
    except ValueError:
        return None

    if not TOOL_ROOT.exists():
        return None

    target = _normalize(Path(nombre).name)
    files = [p for p in TOOL_ROOT.rglob("*") if p.is_file() and not p.name.startswith(".")]
    if not files:
        return None

    for path in files:
        if _normalize(path.name) == target:
            return path
    for path in files:
        if _normalize(path.stem) == _normalize(Path(nombre).stem):
            return path
    for path in files:
        normalized = _normalize(path.name)
        if target in normalized or normalized in target:
            return path

    close = difflib.get_close_matches(
        target, [_normalize(p.name) for p in files], n=1, cutoff=0.4
    )
    if close:
        for path in files:
            if _normalize(path.name) == close[0]:
                return path
    return None


def _menciona_archivo(message: str) -> str | None:
    """Detecta si el usuario pide leer un archivo concreto y lo resuelve.

    Los modelos de 3B piden el nombre del archivo aunque esté delante, así que
    cuando la petición apunta a un archivo se entrega el contenido en el
    contexto en vez de confiar en el bucle de herramientas.
    """
    if not TOOL_ROOT.exists():
        return None
    texto = _normalize(message)
    pistas = ("archivo", "fichero", "documento", "nota", "txt", "pdf", "lee", "resume")
    if not any(p in texto for p in pistas):
        return None
    files = [
        p for p in sorted(TOOL_ROOT.rglob("*"))
        if p.is_file() and not p.name.startswith(".")
    ]
    for path in files:
        if _normalize(path.name) in texto or _normalize(path.stem) in texto:
            return path.name
    # Sin nombre explícito («el archivo de notas») y un único candidato: se usa
    # ese. Si el usuario nombró un archivo con extensión o una ruta y no existe,
    # no se adivina, para no leer un documento equivocado.
    if re.search(r"\w+\.(txt|md|pdf|csv|json|log)\b", texto) or "/" in texto or ".." in texto:
        return None
    return files[0].name if len(files) == 1 else None


def listar_archivos() -> str:
    if not TOOL_ROOT.exists():
        return "El espacio de trabajo está vacío."
    files = [
        f"- {p.name} ({p.stat().st_size} bytes)"
        for p in sorted(TOOL_ROOT.rglob("*"))
        if p.is_file() and not p.name.startswith(".")
    ]
    return "\n".join(files) if files else "El espacio de trabajo está vacío."


def leer_archivo(nombre: str) -> str:
    path = _resolve(nombre)
    if path is None:
        return f"No existe '{nombre}'. Archivos disponibles:\n{listar_archivos()}"
    if path.stat().st_size > MAX_FILE_BYTES:
        return (
            f"'{path.name}' es demasiado grande ({path.stat().st_size} bytes). "
            "Pide al usuario que lo divida."
        )
    try:
        return path.read_text(encoding="utf-8")[:MAX_FILE_BYTES]
    except UnicodeDecodeError:
        return f"'{path.name}' no parece ser un archivo de texto."


async def buscar_en_wikipedia(consulta: str) -> str:
    params = {
        "action": "query",
        "list": "search",
        "srsearch": consulta,
        "format": "json",
        "srlimit": MAX_RESULTS,
        "utf8": 1,
    }
    headers = {"User-Agent": WIKI_UA}
    try:
        async with httpx.AsyncClient(timeout=20.0, headers=headers) as client:
            response = await client.get(
                "https://es.wikipedia.org/w/api.php", params=params
            )
            response.raise_for_status()
            hits = response.json().get("query", {}).get("search", [])
            if not hits:
                response = await client.get(
                    "https://en.wikipedia.org/w/api.php", params=params
                )
                response.raise_for_status()
                hits = response.json().get("query", {}).get("search", [])
    except Exception as exc:  # noqa: BLE001
        return f"No pude buscar en Wikipedia: {exc}"

    if not hits:
        return f"Sin resultados en Wikipedia para '{consulta}'."

    lines = []
    for hit in hits:
        snippet = (
            hit.get("snippet", "")
            .replace('<span class="searchmatch">', "")
            .replace("</span>", "")
            .replace("&quot;", '"')
            .replace("&amp;", "&")
        )
        lines.append(f"- {hit['title']}: {snippet}")
    return "\n".join(lines)


def fecha_y_hora() -> str:
    now = datetime.now()
    dias = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
    meses = [
        "enero", "febrero", "marzo", "abril", "mayo", "junio",
        "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
    ]
    return (
        f"{dias[now.weekday()]}, {now.day} de {meses[now.month - 1]} "
        f"de {now.year}, {now.strftime('%H:%M')}"
    )


async def run_tool(name: str, args: dict) -> tuple[str, str]:
    """Ejecuta una herramienta y devuelve (resultado, resumen para la interfaz)."""
    try:
        if name == "listar_archivos":
            return listar_archivos(), "Revisando el espacio de trabajo"
        if name == "leer_archivo":
            nombre = str(args.get("nombre", ""))
            path = _resolve(nombre)
            return leer_archivo(nombre), f"Leyendo {path.name if path else nombre}"
        if name == "buscar_en_wikipedia":
            consulta = str(args.get("consulta", ""))
            return await buscar_en_wikipedia(consulta), f"Buscando «{consulta}»"
        if name == "fecha_y_hora":
            return fecha_y_hora(), "Consultando la fecha"
        return f"Herramienta desconocida: {name}", f"Herramienta desconocida: {name}"
    except Exception as exc:  # noqa: BLE001
        return f"Error al ejecutar {name}: {exc}", f"Error en {name}"
