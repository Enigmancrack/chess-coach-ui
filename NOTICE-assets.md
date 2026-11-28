# Third-party assets and licences

## Code

The original code in this repository is licensed under the GNU General Public
License v3.0 or later; see `LICENSE`. The project depends on `python-chess` and
Stockfish, both GPL-3.0-or-later.

## Vendored artwork and sounds

`static/vendor/` contains board and piece artwork and sounds in the style of
chess.com. **They are not covered by the GPL and are not licensed for
redistribution.** They are present for personal local use only. If you fork or
redistribute this repository, remove `static/vendor/` first and supply your own
assets under a licence you can comply with.

The application does not require those exact files to run; it requires a board
theme, piece set and sound theme in the expected layout.
