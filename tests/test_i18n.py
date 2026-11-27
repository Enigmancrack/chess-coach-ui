"""The translation catalog: completeness, plurals and language-neutral ids."""
from __future__ import annotations

from typing import Any

import chess
import pytest

import i18n
import review


def flatten(catalog: Any) -> set[str]:
    keys: set[str] = set()
    for section, values in catalog.items():
        for name in values:
            keys.add(f"{section}.{name}")
    return keys


def test_every_key_exists_in_every_language():
    catalogs = {lang: flatten(i18n.STRINGS[lang]) for lang in i18n.LANGS}
    base = catalogs[i18n.DEFAULT_LANG]
    assert base, "the catalog must not be empty"
    for lang, keys in catalogs.items():
        assert keys == base, (lang, sorted(base - keys), sorted(keys - base))


def test_missing_key_raises_instead_of_falling_back():
    with pytest.raises(KeyError):
        i18n.t("coach.does_not_exist", "cs")
    with pytest.raises(KeyError):
        i18n.t("no_such_section.at_all", "en")


def test_czech_plurals_for_one_two_and_five():
    assert i18n.plural("games", 1) == "partie"
    assert i18n.plural("games", 2) == "partie"
    assert i18n.plural("games", 5) == "partií"
    assert i18n.plural("games", 0) == "partií"
    assert i18n.plural("games", 21) == "partií"
    assert i18n.plural("moves", 1) == "tah"
    assert i18n.plural("moves", 3) == "tahy"
    assert i18n.plural("moves", 9) == "tahů"
    assert i18n.plural("plies", 2) == "půltahy"


def test_english_plurals_for_one_and_many():
    assert i18n.plural("games", 1, "en") == "game"
    assert i18n.plural("games", 5, "en") == "games"
    assert i18n.plural("moves", 1, "en") == "move"
    assert i18n.plural("moves", 2, "en") == "moves"


def test_language_resolution_defaults_to_czech(monkeypatch):
    monkeypatch.delenv("COACH_LANG", raising=False)
    assert i18n.resolve() == "cs"
    monkeypatch.setenv("COACH_LANG", "en")
    assert i18n.resolve() == "en"
    monkeypatch.setenv("COACH_LANG", "de")
    assert i18n.resolve() == "cs"          # invalid env never breaks a run
    assert i18n.resolve("en") == "en"


def test_category_labels_cover_every_category_and_keep_ids():
    assert set(i18n.category_labels("cs")) == set(review.CATEGORIES)
    assert set(i18n.category_labels("en")) == set(review.CATEGORIES)
    assert i18n.category_label("blunder", "cs") == "Hrubka"
    assert i18n.category_label("blunder", "en") == "Blunder"


def test_coach_sentence_is_localized_but_the_verdict_id_is_not():
    rec = {"san": "Qh5", "uci": "d1h5", "best": "Nf3", "best_uci": "g1f3",
           "loss": 400}
    cs = review.coach_sentence(rec, "cs")
    en = review.coach_sentence(rec, "en")
    assert review.classify(rec) == "blunder"
    assert "hrubka" in cs and "Better" not in cs
    assert "blunder" in en and "lepší" not in en
    assert "Nf3" in cs and "Nf3" in en         # SAN is language-neutral


def test_evaluate_move_keeps_numbers_and_switches_text():
    board = chess.Board()
    move = chess.Move.from_uci("e2e4")
    cs = review.evaluate_move(board, move, [], [], 1, "cs")
    en = review.evaluate_move(board, move, [], [], 1, "en")
    assert cs["verdict"] == en["verdict"] == "book"
    assert cs["loss"] == en["loss"] == 0
    assert cs["uci"] == en["uci"] == "e2e4"
    assert cs["label"] == "Teorie" and en["label"] == "Book"
    assert "teorie" in cs["text"] and "book" in en["text"]


def test_verdict_sentence_is_localized():
    knowledge = {"elo_estimate": 900, "weakness": "weak_endgame"}
    report = {"accuracy": 91.0, "counts": {"blunder": 3}}
    cs = review.verdict_sentence(knowledge, report, "cs")
    en = review.verdict_sentence(knowledge, report, "en")
    assert "Přesnost 91.0 %" in cs and "čistá" in cs
    assert "Accuracy 91.0 %" in en and "clean" in en
    assert "weak endgame" in cs and "weak endgame" in en
    assert "taktika" in cs and "tactics" in en


def test_advice_is_localized():
    report = {"counts": {"blunder": 2, "mistake": 3, "miss": 1},
              "worst": [{"ply": 5, "san": "Qh5", "best": "Nf3"}]}
    cs = review.advice(report, lang="cs")
    en = review.advice(report, lang="en")
    assert any("hrubek" in tip for tip in cs)
    assert any("blunders" in tip for tip in en)
    assert any("Qh5" in tip for tip in cs)
    assert any("Qh5" in tip for tip in en)


def test_coach_cli_switches_language(monkeypatch, tmp_path, capsys):
    import coach

    monkeypatch.delenv("COACH_LANG", raising=False)
    monkeypatch.setenv("COACH_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("COACH_JOURNAL_DIR", str(tmp_path))
    assert coach.main(["games", "--lang", "en"]) == 0
    english = capsys.readouterr().out
    assert "no imported games" in english and "žádné" not in english
    assert coach.main(["--lang", "cs", "games"]) == 0
    czech = capsys.readouterr().out
    assert "žádné importované" in czech
    assert coach.main(["games"]) == 0        # default is Czech
    assert "žádné importované" in capsys.readouterr().out
