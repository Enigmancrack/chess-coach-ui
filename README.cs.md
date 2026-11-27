# chess-coach-ui

[English](README.md) · **Čeština** · [Deutsch](README.de.md) · [Español](README.es.md)

Lokální šachovnice, trenér a poherní review ve stylu chess.com nad
Stockfishem. Vše běží na `127.0.0.1`: žádný účet, žádný cloud, žádný síťový
požadavek za běhu. Desky, figury a zvuky jsou vendornuté v `static/vendor/`
(chess.com artwork, jen pro osobní lokální použití). Stejný kód umí importovat
partie zaznamenané Python botem a zreviewsovat je z botových vlastních evaluací,
bez přehrávání přes engine.

## Co to umí

| Funkce | Co dělá |
|---|---|
| Deska a ovládání | drag & drop i klik–klik, včetně braní kliknutím na soupeřovu figuru; přepnutí výběru kliknutím na jinou vlastní figuru; proměna vždy otevře výběr Q/R/B/N; nelegální UCI se nikdy neodešle |
| Stav desky | výběr, tečky legálních tahů, kroužky braní, žlutě poslední tah obou stran, červený král v šachu, animace tahu 200 ms, během partie se deska nepřekresluje celá |
| Témata | 9 desek, 8 sad figur, 2 zvuková témata (`default`, `beat`), zvuky pro tah, braní, rošádu, šach, proměnu, start/konec, deset sekund a ilegální tah |
| Režimy | `training` (živé odznaky a rady), `sharp` (žádné rady do konce partie), `analysis` (eval vždy viditelný) a read-only `import` |
| Hodiny | server-authoritative pro obě strany: čas se odečítá tomu, kdo je na tahu (i Stockfishe, dokud přemýšlí), po tahu se přičte increment, detekuje se pád vlajky a výsledek |
| Živý trenér | okamžitý odznak (brilliant / great / best / good / book / inaccuracy / mistake / blunder / miss) a jedna věta, co bylo lepší a o kolik centipawnů |
| Review | přesnost, počty kategorií, průměrná ztráta, nejhorší momenty s nejlepší alternativou, canvas eval graf, šipky nejlepší/sehraný tah, ovládání klávesnicí, export PGN |
| Import partií bota | čte `~/.chess_bot_journals/*.jsonl` a `~/.chess_coach_games/*.json`; použije uložené evaluace místo opakovaného spouštění Stockfishe; deník začínající v průběhu partie ukotví na zaznamenaný FEN |
| Terminálový trenér | `coach.py play|review|import|games` pro partii, uložený review, import deníku nebo výpis |

## Rychlý start

```bash
cd ~/projekty/chess-coach-ui

# Systémy s PEP 668 (Kali, Debian) odmítnou instalaci do systému; použij venv.
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# Spuštění serveru (blokuje; Ctrl+C ukončí). `./run.sh` dělá totéž
# se systémovým python3.
.venv/bin/python server.py --port 8770
curl -s http://127.0.0.1:8770/api/health
# {"ok": true, "stockfish": "...", "engine_present": true}
```

Otevři `http://127.0.0.1:8770`. Jiný host, port nebo Stockfish:

```bash
.venv/bin/python server.py --host 127.0.0.1 --port 9000
COACH_STOCKFISH=/cesta/stockfish .venv/bin/python server.py
```

Kontroly:

```bash
.venv/bin/python -m pytest -q
node --check static/app.js
node --check static/motion.js
.venv/bin/python tests/e2e_api.py     # celý API průchod, potřebuje Stockfish (~15 s)
```

Terminálový trenér:

```bash
.venv/bin/python coach.py games
.venv/bin/python coach.py review
.venv/bin/python coach.py import ~/.chess_bot_journals/<partie>.done.jsonl
.venv/bin/python coach.py play --level 8 --player viktor
```

Server odmítne start, pokud Stockfish na cestě není. Statické soubory servíruje
z `static/`, API je pod `/api/*` a autentizace není, protože vše je jen
loopback.

## Konfigurace

| Proměnná | Význam | Default |
|---|---|---|
| `COACH_STOCKFISH` | cesta k Stockfishi | první `stockfish` v `PATH`, jinak známá instalační cesta, jinak autorova build |
| `COACH_DEPTH` | hloubka analýzy při hře | `10` |
| `COACH_REVIEW_DEPTH` | hloubka analýzy pro review | `12` |
| `COACH_DATA_DIR` | kam ukládat JSON partií | `~/.chess_coach_games` |
| `COACH_JOURNAL_DIR` | adresář deníků bota | `~/.chess_bot_journals` |
| `COACH_MODEL_FILE` | model soupeře, jen pro čtení | `~/.chess_opponent_model.json` |
| `COACH_LANG` | jazyk UI (`cs`, `en`) | `cs` |
| `COACH_HTTP_LOG` | `1` zapne HTTP log | vypnuto |

## Architektura

| Soubor | Role |
|---|---|
| `server.py` | stdlib HTTP server, JSON API, statické soubory, životní cyklus her, allowlist pro import |
| `game.py` | jedna partie: deska, hodiny, bot, takeback, review worker, pohled na importovanou partii |
| `rules.py` | legalita, normalizace UCI, flagy tahů, materiál, detekce oběti |
| `clock.py` | serverové hodiny s injektovatelným časem pro testy |
| `engine.py` | adaptér na Stockfish (`analyse`, `play`, úrovně 4–16) |
| `review.py` | klasifikace, accuracy, analýza celé partie, PGN, profil hráče |
| `importer.py` | parsování deníků a uložených partií, ukotvení v průběhu hry, reuse uložených evaluací |
| `coach.py` | terminálový klient |
| `i18n.py` | české a anglické texty UI |
| `data/store.py` | JSON úložiště partií (seam pro pozdější SQLite) |
| `static/` | `index.html`, `style.css`, `app.js`, `motion.js`, vendornuté assety |

API: `GET /api/health|themes|settings|state|review|pgn|games`,
`POST /api/new|move|takeback|resign|review|import|settings`. Chyby jsou JSON se
statusem 400/404/409. `state` vrací FEN, tahy, legální cíle (jen když je na tahu
člověk), hodiny, výsledek, eval a poznámku trenéra.

## Ověření

| Kontrola | Výsledek |
|---|---|
| `python3 -m pytest -q` | **96 prošlo** |
| `node --check static/app.js`, `static/motion.js` | oba čisté |
| `python3 tests/e2e_api.py` | projde end to end proti skutečnému Stockfishi |

E2E běh projde health, témata (9 desek, 8 sad figur, zvuky `beat`/`default`),
novou partii za bílé, odečet hodin (59,997 → 58,793), tah hráče a odpověď bota,
takeback, ilegální tah s 400, partii za černé s úvodním tahem bota, vlastní FEN,
proměnu na poslední řadě s braním a šachem, review (přesnost 87,6 %, průměrná
ztráta 32,0 cp), PGN a rezignaci.

## Omezení

- **Hry z webu se neukládají.** Server drží nejvýš 40 partií v paměti; na disk
  zapisuje jen terminálový trenér a importer.
- **Jeden proces Stockfishe za zámkem.** Review a tah bota se serializují;
  dlouhý review zdrží další odpověď bota.
- **Žádná adaptace na soupeře z importovaných dat, žádné drilly ani spaced
  repetition.** V `data/` je pro ně seam, ale implementované nejsou.
- **Vizuál je ověřený jen syntakticky a přes API.** V prostředí buildu neběžel
  prohlížeč, takže rozměry na malých displejích a přesné barvy nejsou
  zkontrolované.
- **Cesty importu jsou omezené.** Číst se smí jen pod `~/.chess_bot_journals`
  a `~/.chess_coach_games`; cokoli jiného server odmítne s 400.

## Licence

Repo neobsahuje soubor `LICENSE`. `python-chess` a Stockfish jsou
GPL-3.0-or-later, takže distribuovaný bundle, který je obsahuje, spadá pod
GPLv3. Vendornutý chess.com artwork a zvuky nemají licenci k redistribuci
a jsou určené jen pro osobní lokální použití.
