# Chess Coach — první kroky

Lokální šachový kouč: hraješ proti Stockfishe v prohlížeči, kouč ohodnotí každý
tah a po partii dostaneš celý review s grafem evaluace a šipkami. Vše běží na
tvém počítači — žádný účet, žádné připojení k internetu.

## 1. Instalace a spuštění

Potřebuješ Python 3.11+ a binárku Stockfish. Ověř, že je Stockfish dostupný:

```bash
command -v stockfish
```

Když nic nevypíše, nastav `COACH_STOCKFISH` na plnou cestu k binárce ještě před
spuštěním (viz krok 3). Pak v kořeni repozitáře:

```bash
python3 -m venv --system-site-packages .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pytest -q
```

Poslední příkaz spustí testy — `96 passed` znamená, že instalace je v pořádku.
Aplikaci spusť v tomto terminálu:

```bash
./run.sh 8770
```

Vypíše `chess-coach-ui na http://127.0.0.1:8770  (engine …)` a běží, dokud
nestiskneš Ctrl+C. Otevři <http://127.0.0.1:8770>. `./run.sh` odmítne start,
když je port už obsazený.

Ruční start serveru s anglickým koučem:

```bash
python3 server.py --port 8770 --lang en
```

## 2. První partie

Po načtení se otevře dialog „Nová partie“. Vyber:

- **Barva** — Bílá, Černá nebo Náhodně. Za černého udělá server hned první tah
  bílého a deska se otočí, takže tvé figurky jsou dole.
- **Tempo** — předvolba (3|0 … 30|0), nebo vlastní základ v minutách a přírůstek
  v sekundách. Bullet se záměrně nenabízí.
- **Úroveň soupeře** — 4 (začátečník) až 16 (silný klubový hráč).
- **Režim** — Trénink (rada po každém tahu), Ostrá (žádné rady do konce partie)
  nebo Analýza (rady plus eval bar).
- **Jméno** — jméno uložené u partie.

Stiskni **Hrát**. Deska se objeví uprostřed, tvé hodiny dole, soupeřovy nahoře;
panel kouče je vpravo.

Táhni kliknutím na figurku a potom na zvýrazněný cíl, nebo přetáhnutím. Legální
cíle jsou malé tečky, braní kroužek. Povýšení otevře výběr (dáma, věž, střelec,
jezdec). Nemůžeš táhnout, když nejsi na tahu nebo když engine přemýšlí — hodiny
vlastní server, ne prohlížeč, takže se zastaví v okamžiku, kdy tvůj tah dorazí.

Tvé tahy se hned hodnotí v panelu kouče a odznak se objeví i u tahu v seznamu
tahů.

## 3. Co znamenají odznaky

| Odznak | Česky | Význam |
|---|---|---|
| !! | Brilantní | oběť, po které pozice drží |
| ! | Skvělý | jediný tah, který drží |
| * | Nejlepší | tah enginu (nebo stejně dobrý) |
| . | Dobrý | malá ztráta, do 30 centipawnů |
| B | Teorie | zahájení, prvních deset půltahů |
| ?! | Nepřesnost | ztráta 30–90 centipawnů |
| ? | Chyba | ztráta 90–220 centipawnů |
| ?? | Hrubka | ztráta více než 220 centipawnů |
| X | Promarněná výhra | vynucená výhra se neodehrála |

Uložené a porovnávané je id (`best`, `blunder`, …); viditelné slovo je jen
překlad. Jazyk přepneš selectem **Jazyk** v horní liště — text kouče, odznaky
i hlášky nové partie se řídí jím, tahy a výsledky zůstávají ve standardní
notaci.

## 4. Eval bar

Tenký svislý pruh vlevo od desky ukazuje, kdo je lepší. Světlá část patří vždy
hráči, jehož figurky jsou dole, tmavá soupeři; číslo vedle je evaluace v pěšcích
z pohledu bílého (`+1.2` znamená, že bílý je o pěšce a kousek lepší). Pruh se
plynule posouvá, neskáče. V režimu Ostrá je skrytý do konce partie. Tlačítko
**≈** v horní liště ho skryje nebo zobrazí.

## 5. Rady a vrácení tahu

Po každém tvém tahu ukáže karta kouče odznak a jednu větu, např.
`Nf3 je dobrý tah.` Když tah něco stál, přidá se řádek
`Ztráta 120 cp · nejlepší Nf3`. To je celý systém rad: nikdy nenapoví tah
předem, vysvětluje ten, který jsi právě sehrál.

**↶ Vzít tah zpět** vezme tvůj poslední tah *i* odpověď bota, takže jsi znovu na
tahu. Je zakázané, dokud engine přemýšlí, a po konci partie. **Vzdát partii**
partii vzdá; výsledek se uloží jako tvá prohra.

## 6. Jak číst review

Po konci partie se aktivuje **Analyzovat partii**. Stiskni ho: ukazatel průběhu
odpočítá analyzované půltahy a otevře se panel review.

- **Přesnost** — velké číslo vlevo, 0–100 %. Počítá se z poklesu
  pravděpodobnosti výhry, ne z holých centipawnů; 85+ je čistá partie.
- **Podtitulek** — přesnost, kolik tvých tahů se hodnotilo, průměrná ztráta
  v centipawnech, odkud evaluace pochází (deník, uložená partie, Stockfish)
  a zda byly vzorky brány před tvými tahy.
- **Počty** — jeden štítek na odznak s počtem výskytů.
- **Graf** — křivka evaluace celé partie. Horní světlá polovina patří bílému;
  křivka nad středem znamená, že bílý vyhrává. Kliknutím na graf skočíš na
  daný okamžik.
- **Šipky** — na desce je zelená nejlepší tah, červená skutečně sehrávaný tah,
  modrošedá sehrávaný tah bez uložené alternativy (typicky importovaný deník
  bota).
- **Nejhorší momenty** — pět nejdražších chyb. Kliknutím na řádek skočíš na
  daný půltah.
- **← / →** prochází partii; **PGN** stáhne partii.

Review jde kdykoli otevřít znovu; report zůstává v paměti běžící relace.

## 7. Import partie

Kouč umí přehrát partie nahrané doprovodným botem. Do pole v panelu
**Partie bota** vlož cestu k `.jsonl` deníku nebo k uložené `.json` partii
a stiskni **Import**. Přijímají se jen soubory v datových složkách bota
(ve výchozím stavu `~/.chess_bot_journals` a `~/.chess_coach_games`).
Importované partie se objeví v seznamu a otevřou se jen ke čtení: nedá se
táhnout, vracet ani vzdát, ale deska, seznam tahů, review i export PGN fungují
normálně. Uložené evaluace se použijí tak, jak jsou; Stockfish se spustí jen
tehdy, když je deník nemá.

Totéž z terminálu:

```bash
COACH_JOURNAL_DIR=~/.chess_bot_journals COACH_DATA_DIR=~/.chess_coach_games \
  python3 coach.py import ~/.chess_bot_journals/demo.done.jsonl
python3 coach.py games
```

## 8. Hraní a review v terminálu

```bash
python3 coach.py play --level 4 --player demo          # česky (výchozí)
python3 coach.py play --level 4 --player demo --lang en
COACH_LANG=en python3 coach.py review                  # trvalý výchozí jazyk
python3 coach.py review --lang cs
```

`play` vypíše desku, přijímá SAN (`Nf3`) i UCI (`g1f3`) a končí na `quit`;
potom partii zanalyzuje a uloží. `review` otevře poslední uloženou partii (nebo
soubor, který zadáš). Jazyk si můžeš nechat v `COACH_LANG`, abys nemusel
opakovat `--lang`.

## 9. Klávesové zkratky

| Klávesa | Kde | Akce |
|---|---|---|
| ← / → | otevřený review | předchozí / další půltah |
| Esc | otevřený review | zavřít review |
| Esc | výběr povýšení | zrušit povýšení |
| Enter | pole cesty importu | spustit import |

Zbytek obstará myš: kliknutím vybíráš a táhneš, kliknutím na bod grafu nebo
řádek nejhoršího momentu skočíš na dané místo.
