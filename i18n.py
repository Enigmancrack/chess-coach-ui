"""One home for every user-facing string the coach prints or sends.

Machine-readable values (category ids, UCI/SAN, JSON keys, result codes) never
live here: only display text.  Catalogs are TypedDicts, so a language missing a
key is a type error, and `t()` raises `KeyError` at runtime instead of falling
back to another language – a silent fallback would ship half-translated output.

    from i18n import t, plural
    t("errors.game_over", "en")                 # "the game is already over"
    plural("games", 5, "cs")                    # "partií"
"""
from __future__ import annotations

import os
from typing import Any, Final, Literal, TypedDict

Lang = Literal["cs", "en"]
LANGS: Final[tuple[Lang, ...]] = ("cs", "en")
DEFAULT_LANG: Final[Lang] = "cs"
ENV_VAR: Final[str] = "COACH_LANG"


class ErrorText(TypedDict):
    unknown_game: str
    unknown_endpoint: str
    missing_game_path: str
    invalid_fen: str
    invalid_fen_bare: str
    game_over: str
    engine_thinking: str
    not_your_turn: str
    illegal_move: str
    out_of_time: str
    wait_engine: str
    nothing_to_take_back: str
    read_only: str
    review_engine_missing: str
    stockfish_missing: str
    env_hint: str
    unknown_language: str


class CategoryText(TypedDict):
    brilliant: str
    great: str
    best: str
    good: str
    book: str
    inaccuracy: str
    mistake: str
    blunder: str
    miss: str


class CoachText(TypedDict):
    brilliant: str
    great: str
    miss: str
    book: str
    best_equal: str
    best_exact: str
    good: str
    generic: str
    better: str


class ReviewText(TypedDict):
    accuracy: str
    band_clean: str
    band_solid: str
    band_loose: str
    model_elo: str
    weakness: str
    three_blunders: str


class AdviceText(TypedDict):
    blunders: str
    missed_win: str
    mistakes: str
    inaccuracies: str
    clean: str


class InsightText(TypedDict):
    empty: str
    line: str
    elo: str
    variance: str
    style: str
    weakness: str
    games: str
    estimate_only: str
    blank: str


class CliText(TypedDict):
    opponent_move: str
    prompt: str
    ended_early: str
    unclear: str
    move_loss: str
    result: str
    analysing: str
    saved: str
    review_head: str
    review_line: str
    accuracy_bar: str
    worst_head: str
    worst_line: str
    better: str
    no_saved_game: str
    file_missing: str
    error_line: str
    rejected: str
    import_failed: str
    import_title: str
    import_who: str
    import_date: str
    import_result: str
    import_termination: str
    import_review: str
    import_no_review: str
    source_journal: str
    source_stored: str
    source_engine: str
    eval_note: str
    no_imports: str
    import_hint: str
    list_date: str
    list_result: str
    list_moves: str
    list_accuracy: str
    list_opponent: str
    list_footer: str
    stopped: str
    help_play: str
    help_review: str
    help_import: str
    help_games: str
    help_import_file: str
    help_lang: str


class ServerText(TypedDict):
    start: str
    description: str


class PgnText(TypedDict):
    bot_name: str


class CommonText(TypedDict):
    opponent: str


class Catalog(TypedDict):
    errors: ErrorText
    categories: CategoryText
    coach: CoachText
    review: ReviewText
    advice: AdviceText
    insight: InsightText
    cli: CliText
    server: ServerText
    pgn: PgnText
    common: CommonText


class PluralText(TypedDict):
    plies: tuple[str, ...]
    moves: tuple[str, ...]
    games: tuple[str, ...]


STRINGS: Final[dict[Lang, Catalog]] = {}


def _plural_cs(forms: tuple[str, ...], count: int) -> str:
    """Czech: 1 partie / 2 partie / 5 partií."""
    number = abs(int(count))
    if number == 1:
        return forms[0]
    if 2 <= number <= 4:
        return forms[1]
    return forms[2]


def _plural_en(forms: tuple[str, ...], count: int) -> str:
    return forms[0] if abs(int(count)) == 1 else forms[1]


PLURALS: Final[dict[Lang, PluralText]] = {
    "cs": {
        "plies": ("půltah", "půltahy", "půltahů"),
        "moves": ("tah", "tahy", "tahů"),
        "games": ("partie", "partie", "partií"),
    },
    "en": {
        "plies": ("ply", "plies"),
        "moves": ("move", "moves"),
        "games": ("game", "games"),
    },
}


def is_lang(value: object) -> bool:
    """True for exactly one of the supported language codes."""
    return isinstance(value, str) and value in LANGS


def default_lang() -> Lang:
    """`COACH_LANG` when valid, else Czech."""
    value = os.environ.get(ENV_VAR)
    return value if is_lang(value) else DEFAULT_LANG  # type: ignore[return-value]


def resolve(value: str | None = None) -> Lang:
    """An explicit language wins; otherwise the environment, else the default."""
    if value is None:
        return default_lang()
    return value if is_lang(value) else default_lang()  # type: ignore[return-value]


def t(key: str, lang: str | None = None, **values: Any) -> str:
    """Look up `section.name` and fill its placeholders.

    A missing section or key raises `KeyError` – deliberately, so tests and the
    first run of a new language fail loudly instead of printing the other one.
    """
    section, _, name = key.partition(".")
    catalog = STRINGS[resolve(lang)]
    if not name or section not in catalog:
        raise KeyError(f"missing translation: {key}")
    try:
        text = catalog[section][name]  # type: ignore[literal-required]
    except KeyError:
        raise KeyError(f"missing translation: {key}") from None
    return text.format(**values)


def plural(name: str, count: int, lang: str | None = None) -> str:
    """The right word form for a count in the given language."""
    forms = PLURALS[resolve(lang)][name]  # type: ignore[literal-required]
    return _plural_cs(forms, count) if resolve(lang) == "cs" else _plural_en(forms, count)


def category_label(category: str, lang: str | None = None) -> str:
    """Display label for a category id; the id itself is never translated."""
    return t(f"categories.{category}", lang)


def category_labels(lang: str | None = None) -> dict[str, str]:
    return {key: t(f"categories.{key}", lang)
            for key in sorted(CategoryText.__required_keys__)}


STRINGS["cs"] = {
    "errors": {
        "unknown_game": "neznámá partie",
        "unknown_endpoint": "neznámý endpoint",
        "missing_game_path": "chybí cesta k partii",
        "invalid_fen": "neplatná FEN: {error}",
        "invalid_fen_bare": "neplatná FEN",
        "game_over": "partie už skončila",
        "engine_thinking": "engine právě přemýšlí",
        "not_your_turn": "nejsi na tahu",
        "illegal_move": "nelegální tah",
        "out_of_time": "vypršel čas",
        "wait_engine": "počkej, engine přemýšlí",
        "nothing_to_take_back": "není co vracet",
        "read_only": "importovaná partie je jen ke čtení",
        "review_engine_missing": "chybí engine pro dopočítání review",
        "stockfish_missing": "Stockfish nenalezen: {path}",
        "env_hint": "Nastav COACH_STOCKFISH.",
        "unknown_language": "neznámý jazyk: {value}",
    },
    "categories": {
        "brilliant": "Brilantní",
        "great": "Skvělý",
        "best": "Nejlepší",
        "good": "Dobrý",
        "book": "Teorie",
        "inaccuracy": "Nepřesnost",
        "mistake": "Chyba",
        "blunder": "Hrubka",
        "miss": "Promarněná výhra",
    },
    "coach": {
        "brilliant": "{san} je brilantní oběť — pozice drží.",
        "great": "{san} je jediný tah, který drží.",
        "miss": "Promarněná výhra: {san}.",
        "book": "{san} je teorie.",
        "best_equal": "{san} — stejně dobré jako {best}.",
        "best_exact": "{san} — přesně podle enginu.",
        "good": "{san} je dobrý tah.",
        "generic": "{san} je {label}.",
        "better": " Lepší bylo {best} (−{loss} cp).",
    },
    "review": {
        "accuracy": "Přesnost {accuracy} % ({band}).",
        "band_clean": "čistá",
        "band_solid": "solidní",
        "band_loose": "volnější",
        "model_elo": "Model tě odhaduje na {elo} Elo.",
        "weakness": "Známá slabina: {weakness}.",
        "three_blunders": "Tři a více hrubek — příště taktika.",
    },
    "advice": {
        "blunders": "{blunders} hrubek: před každým braním nebo šachem si "
                    "řekni, co soupeř bere. Začni tou nejhorší (tah "
                    "{ply}, {san} — {best} bylo lepší).",
        "missed_win": "Měl jsi vynucenou výhru a pustil ji — trénuj matové obrazy.",
        "mistakes": "{mistakes} chyb: zpomal ve střední hře, jeden kandidát.",
        "inaccuracies": "Hodně malých nepřesností: kontroluj celou desku každý tah.",
        "clean": "Čistá partie. Zvedni úroveň o jedna a hraj stejně.",
    },
    "insight": {
        "empty": "  model si o soupeři nic nepamatuje.",
        "line": "  model si o soupeři myslí (read-only z botu): {body}",
        "elo": "elo≈{elo}",
        "variance": " (σ {variance})",
        "style": "styl {style}",
        "weakness": "slabina {weakness}",
        "games": "{count} {games} ({wins}-{losses}-{draws})",
        "estimate_only": "bez sehrávek — jen odhad",
        "blank": "jen prázdný záznam",
    },
    "cli": {
        "opponent_move": "  soupeř: {san}",
        "prompt": "\n  tvůj tah (SAN/UCI), 'quit' ukončí: ",
        "ended_early": "  konec předčasně",
        "unclear": "  nerozumím / nelegální tah",
        "move_loss": "  (−{loss} cp, lepší {best})",
        "result": "\n  výsledek: {result}   ({plies} {plies_word})",
        "analysing": "  analyzuji partii…",
        "saved": "  uloženo: {path}",
        "review_head": "  REVIEW  {player}  vs  engine (lvl {level})",
        "review_line": "  výsledek {result}  ·  {moves} {moves_word}"
                       "  ·  průměrná ztráta {avg} cp",
        "accuracy_bar": "  přesnost {accuracy} %  {bar}",
        "worst_head": "\n  nejhorší momenty:",
        "worst_line": "   ply {ply:>3}  {san:<6} {verdict:<11} −{loss} cp{better}",
        "better": " lepší: {best}",
        "no_saved_game": "žádná uložená partie",
        "file_missing": "soubor neexistuje: {path}",
        "error_line": "  {error}",
        "rejected": "  odmítnuto: {error}",
        "import_failed": "  import selhal: {error}",
        "import_title": "  IMPORT  {name}",
        "import_who": "  {who} vs {other}",
        "import_date": "  datum  {date}   ·   čas {time_control}",
        "import_result": "  výsledek {result} ({label})   ·   {moves} {moves_word}",
        "import_termination": "   ·   {termination}",
        "import_review": "  review {source}{note}   ·   přesnost "
                         "{accuracy:.1f} %   ·   průměrná ztráta {avg} cp",
        "import_no_review": "  review není v datech — otevři partii v aplikaci, "
                            "dopočítá Stockfish",
        "source_journal": "z deníku",
        "source_stored": "z uložené partie",
        "source_engine": "Stockfish",
        "eval_note": " — eval před tvými tahy",
        "no_imports": "  žádné importované partie ({dir})",
        "import_hint": "  naimportuj: python3 coach.py import "
                       "~/.chess_bot_journals/<game>.jsonl",
        "list_date": "datum",
        "list_result": "výsledek",
        "list_moves": "tahy",
        "list_accuracy": "přesnost",
        "list_opponent": "soupeř",
        "list_footer": "\n  {count} {games_word} · {dir}",
        "stopped": "\n  ukončeno",
        "help_play": "hrát partii a dostat review",
        "help_review": "review uložené partie",
        "help_import": "naimportovat partii bota",
        "help_games": "seznam importovaných partií",
        "help_import_file": ".jsonl deník nebo .json partie",
        "help_lang": "jazyk výstupu",
    },
    "server": {
        "start": "chess-coach-ui na http://{host}:{port}  (engine {engine})",
        "description": "Lokální šachový kouč",
    },
    "pgn": {"bot_name": "Stockfish lvl {level}"},
    "common": {"opponent": "soupeř"},
}

STRINGS["en"] = {
    "errors": {
        "unknown_game": "unknown game",
        "unknown_endpoint": "unknown endpoint",
        "missing_game_path": "missing path to a game",
        "invalid_fen": "invalid FEN: {error}",
        "invalid_fen_bare": "invalid FEN",
        "game_over": "the game is already over",
        "engine_thinking": "the engine is thinking",
        "not_your_turn": "it is not your turn",
        "illegal_move": "illegal move",
        "out_of_time": "time is up",
        "wait_engine": "wait, the engine is thinking",
        "nothing_to_take_back": "nothing to take back",
        "read_only": "an imported game is read-only",
        "review_engine_missing": "no engine available to compute the review",
        "stockfish_missing": "Stockfish not found: {path}",
        "env_hint": "Set COACH_STOCKFISH.",
        "unknown_language": "unknown language: {value}",
    },
    "categories": {
        "brilliant": "Brilliant",
        "great": "Great",
        "best": "Best",
        "good": "Good",
        "book": "Book",
        "inaccuracy": "Inaccuracy",
        "mistake": "Mistake",
        "blunder": "Blunder",
        "miss": "Missed win",
    },
    "coach": {
        "brilliant": "{san} is a brilliant sacrifice — the position holds.",
        "great": "{san} is the only move that holds.",
        "miss": "Missed win: {san}.",
        "book": "{san} is book.",
        "best_equal": "{san} — as good as {best}.",
        "best_exact": "{san} — exactly what the engine wanted.",
        "good": "{san} is a good move.",
        "generic": "{san} is classed as {label}.",
        "better": " Better was {best} (−{loss} cp).",
    },
    "review": {
        "accuracy": "Accuracy {accuracy} % ({band}).",
        "band_clean": "clean",
        "band_solid": "solid",
        "band_loose": "loose",
        "model_elo": "The model rates you at about {elo} Elo.",
        "weakness": "Known weakness: {weakness}.",
        "three_blunders": "Three or more blunders — practise tactics.",
    },
    "advice": {
        "blunders": "{blunders} blunders: before every capture or check, say "
                    "what the opponent takes. Start with the worst one (move "
                    "{ply}, {san} — {best} was better).",
        "missed_win": "You had a forced win and let it go — practise mating patterns.",
        "mistakes": "{mistakes} mistakes: slow down in the middlegame, "
                    "one candidate move.",
        "inaccuracies": "Many small inaccuracies: scan the whole board on every move.",
        "clean": "A clean game. Raise the level by one and play like this.",
    },
    "insight": {
        "empty": "  the model remembers nothing about this opponent.",
        "line": "  what the model thinks about the opponent (read-only from the bot): {body}",
        "elo": "elo≈{elo}",
        "variance": " (σ {variance})",
        "style": "style {style}",
        "weakness": "weakness {weakness}",
        "games": "{count} {games} ({wins}-{losses}-{draws})",
        "estimate_only": "no games yet — estimate only",
        "blank": "an empty record",
    },
    "cli": {
        "opponent_move": "  opponent: {san}",
        "prompt": "\n  your move (SAN/UCI), 'quit' to end: ",
        "ended_early": "  ended early",
        "unclear": "  I do not understand / illegal move",
        "move_loss": "  (−{loss} cp, better {best})",
        "result": "\n  result: {result}   ({plies} {plies_word})",
        "analysing": "  analysing the game…",
        "saved": "  saved: {path}",
        "review_head": "  REVIEW  {player}  vs  engine (lvl {level})",
        "review_line": "  result {result}  ·  {moves} {moves_word}"
                       "  ·  average loss {avg} cp",
        "accuracy_bar": "  accuracy {accuracy} %  {bar}",
        "worst_head": "\n  worst moments:",
        "worst_line": "   ply {ply:>3}  {san:<6} {verdict:<11} −{loss} cp{better}",
        "better": " better: {best}",
        "no_saved_game": "no saved game",
        "file_missing": "file does not exist: {path}",
        "error_line": "  {error}",
        "rejected": "  rejected: {error}",
        "import_failed": "  import failed: {error}",
        "import_title": "  IMPORT  {name}",
        "import_who": "  {who} vs {other}",
        "import_date": "  date  {date}   ·   time {time_control}",
        "import_result": "  result {result} ({label})   ·   {moves} {moves_word}",
        "import_termination": "   ·   {termination}",
        "import_review": "  review {source}{note}   ·   accuracy "
                         "{accuracy:.1f} %   ·   average loss {avg} cp",
        "import_no_review": "  no review in the data — open the game in the app "
                            "and Stockfish will compute it",
        "source_journal": "from the journal",
        "source_stored": "from the saved game",
        "source_engine": "Stockfish",
        "eval_note": " — eval before your moves",
        "no_imports": "  no imported games ({dir})",
        "import_hint": "  import one: python3 coach.py import "
                       "~/.chess_bot_journals/<game>.jsonl",
        "list_date": "date",
        "list_result": "result",
        "list_moves": "moves",
        "list_accuracy": "accuracy",
        "list_opponent": "opponent",
        "list_footer": "\n  {count} {games_word} · {dir}",
        "stopped": "\n  stopped",
        "help_play": "play a game and get the review",
        "help_review": "review a saved game",
        "help_import": "import one of the bot's games",
        "help_games": "list imported games",
        "help_import_file": ".jsonl journal or .json game",
        "help_lang": "output language",
    },
    "server": {
        "start": "chess-coach-ui on http://{host}:{port}  (engine {engine})",
        "description": "Local chess coach",
    },
    "pgn": {"bot_name": "Stockfish lvl {level}"},
    "common": {"opponent": "opponent"},
}


def _key_shape(catalog: Any) -> dict[str, set[str]]:
    return {section: set(values) for section, values in catalog.items()}


def check_catalogs() -> None:
    """Fail at import time when a language drifts from the others."""
    first = _key_shape(STRINGS[DEFAULT_LANG])
    for lang in LANGS[1:]:
        other = _key_shape(STRINGS[lang])
        if first != other:
            missing = {section: sorted(first.get(section, set()) - other.get(section, set()))
                       for section in set(first) | set(other)}
            extra = {section: sorted(other.get(section, set()) - first.get(section, set()))
                     for section in set(first) | set(other)}
            raise RuntimeError(f"translation catalogs differ for {lang}: "
                               f"missing={missing} extra={extra}")


check_catalogs()
