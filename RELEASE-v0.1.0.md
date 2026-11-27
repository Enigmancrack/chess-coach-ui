# chess-coach-ui v0.1.0

Lokální šachový coach — deska jako na chess.com, trenér a review, bez cloudu.

## Co umí

- desky a figury z chess.com artu (9 desek, 8 sad figur), zvuky (2 sady)
- drag & drop i klik→klik (včetně braní kliknutím), žluté označení posledního tahu
- animace tahu 200 ms s lidským feelingem, proměna s výběrem figury
- hodiny oběma stranám (server-authoritative, i botovi utíká čas při přemýšlení)
- režimy: **Trénink** (odznaky a rady živě) / **Ostrá partie** (rady až po konci)
- review jako na chess.com: přesnost, kategorie, eval graf, šipky, PGN
- import partií bota z `~/.chess_bot_journals`
- terminálový coach: `python3 coach.py play --level 8 --player jméno`

## Ověřeno

69+ testů (pytest), `lsp-diag` čisté, `node --check` na JS, E2E přes API.

## Spuštění

```bash
./run.sh          # http://127.0.0.1:8770, Ctrl+C ukončí
```
