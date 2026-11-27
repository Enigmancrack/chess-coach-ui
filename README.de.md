# chess-coach-ui

[English](README.md) · [Čeština](README.cs.md) · **Deutsch** · [Español](README.es.md)

Lokales Schachbrett, Trainer und Partienachbesprechung im Stil von chess.com,
angetrieben von Stockfish. Alles läuft auf `127.0.0.1`: kein Konto, keine Cloud,
keine Netzwerkanfrage zur Laufzeit. Bretter, Figuren und Klänge liegen unter
`static/vendor/` (chess.com-Artwork, nur für persönliche lokale Nutzung). Derselbe
Code importiert auch Partien des Python-Bots und bespricht sie anhand der
gespeicherten Bewertungen des Bots, ohne sie durch eine Engine zu schicken.

## Funktionen

| Funktion | Was sie tut |
|---|---|
| Brett und Bedienung | Drag & Drop und Klick–Klick, auch Schlagen per Klick auf die gegnerische Figur; Auswahlwechsel per Klick auf eine eigene Figur; Umwandlung öffnet immer die Auswahl D/T/L/S; illegales UCI wird nie gesendet |
| Brettzustand | Auswahl, Punkte für legale Züge, Ringe für Schlagzüge, letzter Zug beider Seiten gelb, roter König bei Schach, 200-ms-Zuganimation, kein vollständiges Neuzeichnen während der Partie |
| Themes | 9 Bretter, 8 Figurensätze, 2 Klangthemen (`default`, `beat`), Klänge für Zug, Schlagen, Rochade, Schach, Umwandlung, Start/Ende, zehn Sekunden und illegalen Zug |
| Modi | `training` (live Abzeichen und Hinweise), `sharp` (keine Hinweise bis zum Partieende), `analysis` (Bewertung immer sichtbar) sowie `import` nur zum Lesen |
| Uhr | serverseitig autoritativ für beide Seiten: die Zeit der Seite am Zug läuft ab (auch die von Stockfish, solange es rechnet), Inkrement nach dem Zug, Flaggenfall und Ergebnis |
| Live-Trainer | sofortiges Abzeichen (brilliant / great / best / good / book / inaccuracy / mistake / blunder / miss) und ein Satz dazu, was besser war und um wie viele Centipawns |
| Nachbesprechung | Genauigkeit, Kategoriezahlen, durchschnittlicher Verlust, schlechteste Momente mit der besten Alternative, Eval-Grafik auf Canvas, Pfeile für besten/gespielten Zug, Tastatursteuerung, PGN-Export |
| Import von Botpartien | liest `~/.chess_bot_journals/*.jsonl` und `~/.chess_coach_games/*.json`; nutzt gespeicherte Bewertungen statt Stockfish erneut zu starten; Journale, die mitten in der Partie beginnen, werden am gespeicherten FEN verankert |
| Terminal-Trainer | `coach.py play|review|import|games` für eine Partie, eine gespeicherte Analyse, einen Journal-Import oder eine Liste |

## Schnellstart

```bash
cd ~/projekty/chess-coach-ui

# Systeme mit PEP 668 (Kali, Debian) verweigern eine systemweite pip-Installation; venv nutzen.
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# Server starten (blockiert; Ctrl+C beendet). `./run.sh` macht dasselbe
# mit dem systemweiten python3.
.venv/bin/python server.py --port 8770
curl -s http://127.0.0.1:8770/api/health
# {"ok": true, "stockfish": "...", "engine_present": true}
```

Dann `http://127.0.0.1:8770` öffnen. Anderer Host, Port oder Stockfish:

```bash
.venv/bin/python server.py --host 127.0.0.1 --port 9000
COACH_STOCKFISH=/pfad/zu/stockfish .venv/bin/python server.py
```

Prüfungen:

```bash
.venv/bin/python -m pytest -q
node --check static/app.js
node --check static/motion.js
.venv/bin/python tests/e2e_api.py     # kompletter API-Durchlauf, braucht Stockfish (~15 s)
```

Terminal-Trainer:

```bash
.venv/bin/python coach.py games
.venv/bin/python coach.py review
.venv/bin/python coach.py import ~/.chess_bot_journals/<partie>.done.jsonl
.venv/bin/python coach.py play --level 8 --player viktor
```

Der Server startet nicht, wenn der Stockfish-Pfad fehlt. Statische Dateien
kommen aus `static/`, die API liegt unter `/api/*`, und es gibt keine
Authentifizierung, weil alles nur über Loopback läuft.

## Konfiguration

| Variable | Bedeutung | Standard |
|---|---|---|
| `COACH_STOCKFISH` | Pfad zur Stockfish-Binärdatei | erstes `stockfish` im `PATH`, sonst ein bekannter Installationspfad, sonst der Build des Autors |
| `COACH_DEPTH` | Analysetiefe während der Partie | `10` |
| `COACH_REVIEW_DEPTH` | Analysetiefe für die Nachbesprechung | `12` |
| `COACH_DATA_DIR` | Ablage der Partie-JSONs | `~/.chess_coach_games` |
| `COACH_JOURNAL_DIR` | Journalverzeichnis des Bots | `~/.chess_bot_journals` |
| `COACH_MODEL_FILE` | Gegnermodell, nur lesen | `~/.chess_opponent_model.json` |
| `COACH_LANG` | UI-Sprache (`cs`, `en`) | `cs` |
| `COACH_HTTP_LOG` | `1` aktiviert das HTTP-Log | aus |

## Architektur

| Datei | Rolle |
|---|---|
| `server.py` | HTTP-Server nur mit stdlib, JSON-API, statische Dateien, Spiel-Lebenszyklus, Import-Allowlist |
| `game.py` | eine Partie: Brett, Uhr, Bot, Takeback, Review-Worker, Ansicht einer importierten Partie |
| `rules.py` | Legalität, UCI-Normalisierung, Zugflags, Material, Erkennung von Opfern |
| `clock.py` | Serveruhr mit injizierbarer Zeit für Tests |
| `engine.py` | Stockfish-Adapter (`analyse`, `play`, Stufen 4–16) |
| `review.py` | Klassifikation, Genauigkeit, Analyse der ganzen Partie, PGN, Spielerprofil |
| `importer.py` | Parsen von Journalen und gespeicherten Partien, Verankerung mitten in der Partie, Wiederverwendung gespeicherter Bewertungen |
| `coach.py` | Terminal-Client |
| `i18n.py` | tschechische und englische UI-Texte |
| `data/store.py` | JSON-Spielspeicher (Nahtstelle für ein späteres SQLite) |
| `static/` | `index.html`, `style.css`, `app.js`, `motion.js`, eingebundene Assets |

API: `GET /api/health|themes|settings|state|review|pgn|games`,
`POST /api/new|move|takeback|resign|review|import|settings`. Fehler sind JSON mit
Status 400/404/409. `state` liefert FEN, Züge, legale Ziele (nur wenn der Mensch
am Zug ist), Uhren, Ergebnis, Bewertung und den Trainerhinweis.

## Verifikation

| Prüfung | Ergebnis |
|---|---|
| `python3 -m pytest -q` | **96 bestanden** |
| `node --check static/app.js`, `static/motion.js` | beide sauber |
| `python3 tests/e2e_api.py` | läuft Ende zu Ende gegen echtes Stockfish |

Der E2E-Lauf prüft Health, Themes (9 Bretter, 8 Figurensätze, Klänge
`beat`/`default`), eine neue Partie mit Weiß, den Uhrenabbau (59,997 → 58,793),
einen Spielerzug und die Bot-Antwort, Takeback, einen illegalen Zug mit 400,
eine Partie mit Schwarz samt Bot-Eröffnungszug, ein eigenes FEN, Umwandlung auf
der Grundreihe mit Schlagen und Schach, die Nachbesprechung (Genauigkeit
87,6 %, durchschnittlicher Verlust 32,0 cp), PGN und Aufgabe.

## Grenzen

- **Webpartien werden nicht gespeichert.** Der Server hält höchstens 40 Partien
  im Speicher; nur der Terminal-Trainer und der Importer schreiben JSON auf die
  Platte.
- **Ein Stockfish-Prozess hinter einem Lock.** Nachbesprechung und Bot-Zug
  serialisieren; eine lange Analyse verzögert die nächste Bot-Antwort.
- **Keine Gegneranpassung aus importierten Daten, keine Drills oder Spaced
  Repetition.** In `data/` gibt es dafür eine Nahtstelle, implementiert sind sie
  nicht.
- **Die Optik ist nur syntaktisch und über die API geprüft.** In der
  Build-Umgebung lief kein Browser, daher sind Layout auf kleinen Displays und
  genaue Farben ungeprüft.
- **Importpfade sind beschränkt.** Gelesen wird nur unter
  `~/.chess_bot_journals` und `~/.chess_coach_games`; alles andere lehnt der
  Server mit 400 ab.

## Lizenz

Das Repository enthält keine `LICENSE`-Datei. `python-chess` und Stockfish sind
GPL-3.0-or-later; ein verteiltes Bündel, das beide enthält, fällt unter GPLv3.
Das eingebundene chess.com-Artwork und die Klänge sind nicht zur Weitergabe
lizenziert und nur für die persönliche lokale Nutzung gedacht.
