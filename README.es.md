# chess-coach-ui

[English](README.md) · [Čeština](README.cs.md) · [Deutsch](README.de.md) · **Español**

Tablero de ajedrez local, entrenador y revisión posterior al estilo de
chess.com, con Stockfish detrás. Todo se ejecuta en `127.0.0.1`: sin cuenta, sin
nube y sin peticiones de red en tiempo de ejecución. Los tableros, las piezas y
los sonidos están incluidos en `static/vendor/` (arte de chess.com, solo para uso
local personal). El mismo código importa partidas grabadas por el bot de Python
y las revisa con las evaluaciones que ya guardó el bot, sin volver a pasarlas por
un motor.

## Funciones

| Función | Qué hace |
|---|---|
| Tablero y entrada | arrastrar y soltar y clic–clic, incluida la captura al hacer clic en la pieza rival; cambiar la selección al pulsar otra pieza propia; la promoción abre siempre el selector D/T/A/C; nunca se envía UCI ilegal |
| Estado del tablero | selección, puntos de jugadas legales, anillos de captura, última jugada resaltada para ambos bandos, rey en rojo si hay jaque, animación de 200 ms, sin repintar el tablero entero durante la partida |
| Temas | 9 tableros, 8 juegos de piezas, 2 temas de sonido (`default`, `beat`), sonidos para jugada, captura, enroque, jaque, promoción, inicio/fin, diez segundos y jugada ilegal |
| Modos | `training` (insignias y consejos en vivo), `sharp` (sin consejos hasta el final), `analysis` (evaluación siempre visible) e `import` de solo lectura |
| Reloj | autoritativo en el servidor para ambos bandos: se descuenta al lado que mueve (también a Stockfish mientras piensa), incremento tras la jugada, detección de caída de bandera y resultado |
| Entrenador en vivo | insignia inmediata (brilliant / great / best / good / book / inaccuracy / mistake / blunder / miss) y una frase sobre qué era mejor y por cuántos centipeones |
| Revisión | precisión, recuento por categorías, pérdida media, peores momentos con la mejor alternativa, gráfico de evaluación en canvas, flechas de mejor/jugada, navegación por teclado, exportación PGN |
| Importación de partidas del bot | lee `~/.chess_bot_journals/*.jsonl` y `~/.chess_coach_games/*.json`; reutiliza las evaluaciones guardadas en lugar de relanzar Stockfish; los diarios que empiezan a mitad de partida se anclan al FEN registrado |
| Entrenador de terminal | `coach.py play|review|import|games` para jugar, revisar una partida guardada, importar un diario o listar |

## Inicio rápido

```bash
cd ~/projekty/chess-coach-ui

# Los sistemas con PEP 668 (Kali, Debian) rechazan pip a nivel de sistema; usa un venv.
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# Arrancar el servidor (bloquea; Ctrl+C lo detiene). `./run.sh` hace lo mismo
# con el python3 del sistema.
.venv/bin/python server.py --port 8770
curl -s http://127.0.0.1:8770/api/health
# {"ok": true, "stockfish": "...", "engine_present": true}
```

Abre `http://127.0.0.1:8770`. Otro host, puerto o Stockfish:

```bash
.venv/bin/python server.py --host 127.0.0.1 --port 9000
COACH_STOCKFISH=/ruta/a/stockfish .venv/bin/python server.py
```

Comprobaciones:

```bash
.venv/bin/python -m pytest -q
node --check static/app.js
node --check static/motion.js
.venv/bin/python tests/e2e_api.py     # recorrido completo de la API, necesita Stockfish (~15 s)
```

Entrenador de terminal:

```bash
.venv/bin/python coach.py games
.venv/bin/python coach.py review
.venv/bin/python coach.py import ~/.chess_bot_journals/<partida>.done.jsonl
.venv/bin/python coach.py play --level 8 --player viktor
```

El servidor se niega a arrancar si la ruta de Stockfish no existe. Los archivos
estáticos se sirven desde `static/`, la API vive bajo `/api/*` y no hay
autenticación porque todo es loopback.

## Configuración

| Variable | Significado | Valor por defecto |
|---|---|---|
| `COACH_STOCKFISH` | ruta al binario de Stockfish | primer `stockfish` en `PATH`, si no una ruta de instalación conocida, si no el build del autor |
| `COACH_DEPTH` | profundidad de análisis durante la partida | `10` |
| `COACH_REVIEW_DEPTH` | profundidad de análisis para la revisión | `12` |
| `COACH_DATA_DIR` | dónde se guardan los JSON de partidas | `~/.chess_coach_games` |
| `COACH_JOURNAL_DIR` | directorio de diarios del bot | `~/.chess_bot_journals` |
| `COACH_MODEL_FILE` | modelo del rival, solo lectura | `~/.chess_opponent_model.json` |
| `COACH_LANG` | idioma de la interfaz (`cs`, `en`) | `cs` |
| `COACH_HTTP_LOG` | `1` activa el log HTTP | desactivado |

## Arquitectura

| Archivo | Rol |
|---|---|
| `server.py` | servidor HTTP de stdlib, API JSON, archivos estáticos, ciclo de vida de partidas, lista blanca de importación |
| `game.py` | una partida: tablero, reloj, bot, takeback, worker de revisión, vista de partida importada |
| `rules.py` | legalidad, normalización UCI, indicadores de jugada, material, detección de sacrificio |
| `clock.py` | reloj del servidor con tiempo inyectable para tests |
| `engine.py` | adaptador de Stockfish (`analyse`, `play`, niveles 4–16) |
| `review.py` | clasificación, precisión, análisis de toda la partida, PGN, perfil del jugador |
| `importer.py` | análisis de diarios y partidas guardadas, anclaje a mitad de partida, reutilización de evaluaciones guardadas |
| `coach.py` | cliente de terminal |
| `i18n.py` | textos de interfaz en checo e inglés |
| `data/store.py` | almacén JSON de partidas (costura para un SQLite futuro) |
| `static/` | `index.html`, `style.css`, `app.js`, `motion.js`, recursos incluidos |

API: `GET /api/health|themes|settings|state|review|pgn|games`,
`POST /api/new|move|takeback|resign|review|import|settings`. Los errores son JSON
con estado 400/404/409. `state` devuelve FEN, jugadas, destinos legales (solo
cuando mueve el humano), relojes, resultado, evaluación y la nota del entrenador.

## Verificación

| Comprobación | Resultado |
|---|---|
| `python3 -m pytest -q` | **96 pasan** |
| `node --check static/app.js`, `static/motion.js` | ambos limpios |
| `python3 tests/e2e_api.py` | pasa de extremo a extremo contra Stockfish real |

La ejecución E2E comprueba health, temas (9 tableros, 8 juegos de piezas, sonidos
`beat`/`default`), una partida nueva con blancas, el descuento del reloj
(59,997 → 58,793), una jugada del humano y la respuesta del bot, takeback, una
jugada ilegal que devuelve 400, una partida con negras y la apertura del bot, un
FEN propio, promoción en la última fila con captura y jaque, la revisión
(precisión 87,6 %, pérdida media 32,0 cp), PGN y rendición.

## Limitaciones

- **Las partidas web no se persisten.** El servidor mantiene como máximo 40
  partidas en memoria; solo el entrenador de terminal y el importador escriben
  JSON en disco.
- **Un solo proceso de Stockfish tras un lock.** La revisión y la jugada del bot
  se serializan; una revisión larga retrasa la siguiente respuesta del bot.
- **Sin adaptación al rival con datos importados, sin drills ni repetición
  espaciada.** `data/` tiene la costura, pero no están implementados.
- **El acabado visual solo está verificado sintácticamente y por la API.** En el
  entorno de compilación no se ejecutó ningún navegador, así que la disposición
  en pantallas pequeñas y los colores exactos no están comprobados.
- **Las rutas de importación están restringidas.** Solo se lee bajo
  `~/.chess_bot_journals` y `~/.chess_coach_games`; cualquier otra ruta se
  rechaza con 400.

## Licencia

El repositorio no contiene ningún archivo `LICENSE`. `python-chess` y Stockfish
son GPL-3.0-or-later, así que un paquete distribuido que los incluya queda bajo
GPLv3. El arte y los sonidos de chess.com incluidos no tienen licencia para
redistribución y son solo para uso local personal.
