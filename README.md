# Chess Coach — lokální šachový trenér

Lokální obdoba chess.com „board + coach“ pro trénink jedné partie proti Stockfishe.
Vše běží na `127.0.0.1`, za běhu žádná síť, žádná registrace, žádná externí služba.
Desky, figury a zvuky jsou vendornuté v `static/vendor/` (chess.com artwork, jen pro
osobní lokální použití).

## Co umí

- **Partie**: bílá / černá / náhodně, tempa 3|0, 3|2, 5|0, 5|5, 10|0, 10|5, 15|10,
  30|0 + vlastní základ a přírůstek. Žádný bullet.
- **Ovládání**: drag & drop, klik–klik (i braní kliknutím na soupeřovu figuru),
  přepnutí výběru kliknutím na jinou vlastní figuru. Pěšec na poslední řadě vždy
  otevře výběr dáma / věž / střelec / jezdec; nikdy se neposílá nelegální UCI.
- **Deska**: výběr, tečky legálních tahů, kroužky braní, žlutě oba tahy posledního
  tahu (hráč i bot), červený král v šachu. Figury se posouvají animací, braní mizí;
  během partie se deska nepřekresluje celá.
- **Hodiny**: obě strany, autoritativní na serveru. Server odečítá čas tomu, kdo je
  na tahu (i Stockfishe, dokud přemýšlí), po tahu přičte increment, detekuje pád
  vlajky a vrátí výsledek. UI mezi dotazy dopočítává, ale každý stav znovu srovná.
- **Eval bar** vlevo; v Tréninku skrytelný tlačítkem `≈`, v Ostré skrytý, v Analýze
  vždy. V review se váže na prohlížený půltah.
- **Kouč**: v Tréninku/Analýze okamžitý badge (brilliant / great / best / good /
  book / inaccuracy / mistake / blunder / miss) a věta, co bylo lepší a o kolik cp.
  V Ostré žádné rady do konce partie.
- **Takeback**: vrátí tvůj tah i odpověď bota (u černého nechá úvodní tah bota).
- **Review**: přesnost %, počty kategorií, průměrná ztráta, nejhorší momenty
  s nejlepší alternativou, eval graf (canvas), klik na bod grafu / tah v seznamu /
  nejhorší moment = skok na půltah; zelená šipka = nejlepší tah engine, červená =
  sehráno; `←`/`→`, export PGN.
- **Zvuky** podle události (tah, braní, rošáda, šach, proměna, začátek/konec,
  deset sekund, ilegální tah), přepínač témat `default` / `beat`.
- **Terminál** zůstává: partie v unicode a review na konci.

## Požadavky

- Python 3.10+ (testováno na 3.14) a `python-chess` (`pip install -r requirements.txt`).
- Stockfish binárka. Výchozí cesta:
  `/home/enigma/projekty/_externi/Stockfish/src/stockfish`.
  Přepiš proměnnou `COACH_STOCKFISH` nebo argumentem `--stockfish`.
- Pro testy `pytest`. Pro kontrolu JS `node` (jen vývojově).

## Spuštění

```bash
cd ~/projekty/chess-coach-ui
python3 server.py --port 8770
# otevři http://127.0.0.1:8770
```

Jiný port / host:

```bash
python3 server.py --host 127.0.0.1 --port 9000
COACH_STOCKFISH=/cesta/stockfish python3 server.py
```

Server odmítne start, pokud Stockfish na cestě není. Statické soubory servíruje
přímo z `static/`, API je na `/api/*`. Vše je jen loopback, bez autentizace.

### Proměnné prostředí

| Proměnná | Význam | Default |
|---|---|---|
| `COACH_STOCKFISH` | cesta k Stockfishi | `~/projekty/_externi/Stockfish/src/stockfish` |
| `COACH_DEPTH` | hloubka analýzy tahů při hře | `10` |
| `COACH_REVIEW_DEPTH` | hloubka analýzy review | `12` |
| `COACH_DATA_DIR` | kam ukládat JSON partie | `~/.chess_coach_games` |
| `COACH_HTTP_LOG` | `1` zapne HTTP log | vypnuto |

## Terminálový kouč

```bash
python3 coach.py play --level 8 --player viktor
python3 coach.py play --level 12 --player viktor --color black
python3 coach.py review              # poslední uložená partie
python3 coach.py review cesta.json   # konkrétní soubor
```

Tahy se zadávají jako SAN (`Nf3`) nebo UCI (`g1f3`), `quit` partii ukončí.
Na konci se vypíše review a partie se uloží jako JSON do `COACH_DATA_DIR`.

## Testy a kontroly

```bash
python3 -m pytest -q
node --check static/app.js
python3 tests/e2e_api.py   # celý API průchod, vyžaduje Stockfish (~15 s)
```

Testy pokrývají normalizaci tahů (mj. `d1d8q` na dámu na 8. řadě a braní dámy),
expozici legálních cílů jen hráči na tahu, hodiny (odečet, increment, pád vlajky
obou stran), takeback (bílý/černý, odmítnutí během přemýšlení), klasifikaci,
accuracy a PGN.

## Architektura

| Soubor | Role |
|---|---|
| `server.py` | stdlib HTTP server, JSON API, statické soubory, životní cyklus her |
| `game.py` | jedna partie: deska, hodiny, bot, takeback, review worker |
| `rules.py` | legalita, normalizace UCI, flagy tahů, materiál, oběť |
| `clock.py` | serverové hodiny s injektovatelným časem (testy) |
| `engine.py` | Stockfish adaptér (`analyse`, `play`, úrovně 4–16) |
| `review.py` | klasifikace, accuracy, analýza celé partie, PGN, profil |
| `coach.py` | terminálový klient |
| `data/` | JSON úložiště; seam pro budoucí SQLite/drilly |
| `static/` | `index.html`, `style.css`, `app.js`, vendornuté assety |

API: `GET /api/health|themes|state|review|pgn`, `POST /api/new|move|takeback|resign|review`.
Chyby jsou JSON se statusem 400/404/409. `state` vrací FEN, tahy, legální cíle
(pouze když je na tahu hráč), hodiny, výsledek, eval a poznámku kouče.

## Omezení a další kroky

- Vizuální doladění (rozměry na malých displejích, přesné barvy) chce lidské oko;
  v tomto prostředí neběžel prohlížeč, takže UI je ověřené jen syntakticky a přes API.
- Žádná adaptace na soupeře z externích dat, drilly ani spaced repetition — v `data/`
  je pro ně připravený seam, ale nejsou implementované.
- Stockfish běží jako jeden proces se zámkem; souběžné review a tah bota se serializují.
- Partie se ukládají jen z terminálového kouče. Web drží hry v paměti (max. 40).
