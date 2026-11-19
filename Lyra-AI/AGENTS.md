# Notas del repositorio

## Qué es esto
IA local con personaje customizable. Ollama + FastAPI + interfaz web. Todo corre en local (127.0.0.1:11434).

## Arranque
- `./start.sh` → servidor en el puerto 12000.
- Ollama se arranca solo si no está corriendo.
- Modelo por defecto: `qwen2.5:3b` (CPU ~18 tok/s, ~2 GB).

## Estructura
- `characters/*.yaml` → ficha del personaje (nombre, personalidad, reglas, ejemplos).
- `app/character.py` → carga el YAML y arma el prompt de sistema.
- `app/engine.py` → streaming contra Ollama + bucle de herramientas + historial.
- `app/tools.py` → archivos de `workspace/`, Wikipedia, fecha.
- `app/tts.py` → voz con Piper (descarga el modelo la primera vez).
- `app/memoria.py` → recuerdos persistidos en `data/memory.json`.
- `app/server.py` → API FastAPI.
- `app/cli.py` → modo terminal.

## Puntos clave
- La variable `OH_CHARACTER` elige el personaje; los archivos que empiezan por `_` no se listan.
- La memoria se añade de forma explícita (no la inventa el modelo).
- Los `examples` del YAML son lo que más fija el estilo, más que los adjetivos.
- Si el modelo divaga, bajar `OH_CHARACTER_TEMPERATURE` a 0.6.
- El prompt de sistema se puede ver con `/personaje` en la CLI.

## Lecciones con modelos pequeños (3B)
Con `qwen2.5:3b` el tool-calling es poco fiable, así que el motor resuelve
algunas cosas de forma determinista:
- **Fecha**: va siempre en el prompt (`## Fecha actual`). El modelo inventaba
  fechas en vez de llamar a la herramienta.
- **Archivos**: si el mensaje menciona un archivo, `_menciona_archivo()` lo
  resuelve y su contenido se inyecta ya leído. Si no, el modelo pedía el
  nombre del archivo en bucle.
- **Respuestas vacías**: Ollama devuelve a veces una respuesta sin contenido ni
  tool calls; el motor reintenta sin herramientas y, si falla, responde una
  frase en personaje.
- **Preámbulos**: si el modelo escribe texto antes de llamar a una herramienta,
  se emite `reset` y la interfaz borra esa burbuja.
- **Identidad**: sin un ejemplo few-shot explícito, el modelo se presenta como
  "un modelo de lenguaje" o dice ser ChatGPT.

## Voz
- `piper-tts` sintetiza en CPU. La voz se descarga sola en el primer `/api/tts`.
- Nombre de voz: `<locale>-<hablante>-<calidad>`; la URL de HuggingFace añade
  idioma y hablante como carpetas.
- `models/voices/*.onnx` está en `.gitignore` (63 MB por voz).
