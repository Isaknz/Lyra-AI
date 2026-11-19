# Lyra — una IA local con tu propio personaje

Una IA que vive en tu ordenador. Tiene nombre, personalidad, historia y forma de
hablar propias, te habla en voz alta, lee tus archivos y recuerda lo que le
cuentas. Nada sale de tu máquina: el modelo corre en local con
[Ollama](https://ollama.com) y la voz con [Piper](https://github.com/rhasspy/piper).

![modelo](https://img.shields.io/badge/modelo-qwen2.5%3A3b-8b7cf6) ![local](https://img.shields.io/badge/100%25-local-22d3ee) ![voz](https://img.shields.io/badge/voz-Piper%20es__ES-34d399)

## Instalación

Requisitos: Python 3.10+, ~3 GB de disco y Ollama.

**1. Ollama** — descárgalo de <https://ollama.com/download> (Linux, macOS y
Windows). En Linux/macOS también sirve:

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

**2. El proyecto**

```bash
git clone https://github.com/Isaknz/Lyra-AI.git
cd Lyra-AI
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

**3. Arrancar**

```bash
./start.sh                       # Windows: python -m uvicorn app.server:app --port 12000
```

Abre <http://localhost:12000>. La primera vez descarga el modelo (~2 GB) y la
voz (~60 MB), y arranca Ollama si no estaba corriendo.

> En Windows el lanzador `start.sh` no funciona con doble clic. Arranca Ollama
> desde el menú Inicio y luego ejecuta el comando de uvicorn de arriba.

## Qué incluye

- **Personaje configurable** en YAML: nombre, avatar, personalidad, historia,
  estilo de habla, reglas, límites y ejemplos de diálogo.
- **Voz local**: la IA te lee las respuestas. Botón 🔊 en la cabecera para
  activarla y «Escuchar» en cada mensaje.
- **Herramientas**: leer archivos de la carpeta `workspace/`, buscar en
  Wikipedia y consultar fecha y hora. Con indicador visual de lo que está
  haciendo.
- **Chat web** con streaming token a token y tema oscuro.
- **Modo terminal** (`python -m app.cli`).
- **Memoria persistente** de hechos, que sobrevive a reinicios.
- **Sin nube**: solo habla con `127.0.0.1:11434`.

## Crear tu personaje

```bash
cp characters/_plantilla.yaml characters/mi-ia.yaml
```

Edita el archivo. Los campos que más cambian el resultado:

| Campo | Para qué sirve |
|---|---|
| `name`, `avatar`, `tagline` | Identidad visible en la interfaz |
| `personality` | Lista de rasgos; se convierten en viñetas del prompt |
| `voice.description` | Ritmo, tono, muletillas, uso de humor |
| `backstory` | Coherencia cuando habla de sí misma |
| `rules` | Comportamiento obligatorio (idioma, no inventar, brevedad…) |
| `boundaries` | Temas que evita |
| `examples` | Pares usuario/asistente que fijan el estilo (lo más efectivo) |

Actívalo:

```bash
OH_CHARACTER=mi-ia ./start.sh
```

Puedes tener varios personajes y cambiar en caliente:

```bash
curl -X POST "http://localhost:12000/api/character/reload?name=mi-ia"
```

## Voz

Usa Piper, que sintetiza en CPU al instante y sin internet. La voz por defecto
es `es_ES-davefx-medium` (voz masculina en español de España). Para cambiarla,
busca otra en <https://rhasspy.github.io/piper-samples/> y:

```bash
OH_TTS_VOICE=es_ES-mls_10246-low ./start.sh
```

Si el archivo no existe, `start.sh` intenta descargarlo. Otras voces en español:
`es_ES-sharvard-medium`, `es_MX-claude-high`, `es_ES-carlfm-x_low`.

## Herramientas

El personaje puede usar cuatro herramientas. Solo se ejecutan cuando hacen
falta, y verás un chip como «Leyendo notas.txt…» mientras trabajan.

| Herramienta | Qué hace |
|---|---|
| `listar_archivos` | Lista lo que hay en `workspace/` |
| `leer_archivo` | Lee un archivo de texto de `workspace/` |
| `buscar_en_wikipedia` | Busca en Wikipedia (español, con respaldo en inglés) |
| `fecha_y_hora` | Fecha y hora del equipo |

Para darle documentos, cópialos a `workspace/`:

```bash
cp ~/Documentos/informe.txt workspace/
```

Todo está encerrado ahí: la herramienta rechaza rutas con `..` o absolutas, y
solo lee texto de menos de 40 KB. Desactivar: `OH_CHARACTER_TOOLS=0`.

## Memoria

En la web, botón 🧠. En terminal:

```
/recuerda Le encanta el cine de terror
/memoria
/olvida Le encanta el cine de terror
```

Se guarda en `data/memory.json`. Los recuerdos se añaden de forma explícita: el
modelo nunca los inventa.

## Modelos

Por defecto `qwen2.5:3b` (~2 GB, bueno en español, ~18 tok/s en CPU).
Alternativas:

```bash
ollama pull qwen2.5:7b        # mejor calidad, ~4.7 GB
ollama pull llama3.2:3b       # algo más rápido
OH_CHARACTER_MODEL=qwen2.5:7b ./start.sh
```

Variables de entorno: `OH_CHARACTER`, `OH_CHARACTER_MODEL`,
`OH_CHARACTER_TEMPERATURE` (def. 0.8), `OH_CHARACTER_HISTORY` (def. 16),
`OH_CHARACTER_TOOLS`, `OH_TTS_VOICE`, `OH_TOOL_ROOT`, `OLLAMA_URL`, `PORT`.

## API

| Método | Ruta | Uso |
|---|---|---|
| `GET` | `/api/character` | Ficha del personaje activo |
| `GET` | `/api/health` | Estado de Ollama y del modelo |
| `POST` | `/api/chat` | Chat con streaming SSE |
| `POST` | `/api/tts` | Texto a voz (WAV) |
| `GET` | `/api/tools` | Herramientas y archivos disponibles |
| `POST` | `/api/reset` | Nueva conversación |
| `GET/POST` | `/api/memory` | Leer / añadir recuerdos |
| `DELETE` | `/api/memory?fact=…` | Olvidar un recuerdo |
| `POST` | `/api/character/reload` | Recargar personaje (`?name=`) |

## Estructura

```
app/
  character.py    # carga el YAML y construye el prompt de sistema
  engine.py       # streaming contra Ollama, bucle de herramientas
  tools.py        # archivos, Wikipedia, fecha
  tts.py          # voz con Piper
  memoria.py      # recuerdos persistentes
  server.py       # API FastAPI
  cli.py          # modo terminal
  static/index.html
characters/       # una ficha YAML por personaje
workspace/        # documentos que la IA puede leer
models/voices/    # voces Piper (se descargan solas)
```

## Consejos para un personaje que se sienta vivo

1. Los `examples` pesan más que las listas de adjetivos: escribe 3-5 diálogos
   con la voz exacta que quieres.
2. Sé concreto en `voice`: «frases cortas, sin signos de exclamación» funciona
   mejor que «tono agradable».
3. Si divaga, baja `OH_CHARACTER_TEMPERATURE` a 0.6.
4. Si suena genérico, añade a `rules` una prohibición explícita de las frases
   que no quieres oír.
5. Con un modelo de 3B el modelo a veces pide permiso en vez de actuar; las
   reglas del prompt ya lo empujan a hacerlo, pero un 7B obedece mejor.

## Licencia

MIT. El modelo y las voces tienen sus propias licencias (Qwen2.5: Apache 2.0;
voces Piper: varía según la voz).

