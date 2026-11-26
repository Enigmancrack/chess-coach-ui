"""Chess rules helpers shared by the server, the terminal coach and the tests.

Everything here is pure (no engine, no clock), which is what makes the edge
cases testable: stray promotion letters, legal-destination exposure and the
per-move flags the UI needs for sounds and highlighting.
"""
from __future__ import annotations

import chess

#: Engine scores are clamped before they are turned into a centipawn loss, so a
#: "mate in 2" (10000) does not dwarf a normal 3-pawn mistake.
CP_LIMIT = 1000
MATE_CP = 10000

PIECE_VALUE = {
    chess.PAWN: 100,
    chess.KNIGHT: 320,
    chess.BISHOP: 330,
    chess.ROOK: 500,
    chess.QUEEN: 900,
    chess.KING: 0,
}

PROMOTION_PIECES = {
    "q": chess.QUEEN,
    "r": chess.ROOK,
    "b": chess.BISHOP,
    "n": chess.KNIGHT,
}


def clamp_cp(cp: int, limit: int = CP_LIMIT) -> int:
    return max(-limit, min(limit, int(cp)))


def white_cp(cp: int, turn: chess.Color) -> int:
    """Convert a side-to-move score to the white point of view."""
    return int(cp) if turn == chess.WHITE else -int(cp)


def normalise_uci(board: chess.Board, raw: str) -> chess.Move | None:
    """Return a legal move for `raw`, or None.

    The UI must not invent promotions for pieces that cannot promote.  A queen
    on d1 capturing on d8 can be sent as ``d1d8q`` by an over-eager client; the
    letter is stripped before the move is called illegal.  The reverse (a pawn
    reaching the last rank without a letter) is completed with a queen so a
    hand-written API call still works.
    """
    text = str(raw or "").strip().lower()
    if len(text) not in (4, 5):
        return None
    try:
        move = chess.Move.from_uci(text)
    except ValueError:
        return None

    if move in board.legal_moves:
        return move

    if len(text) == 5:
        try:
            stripped = chess.Move.from_uci(text[:4])
        except ValueError:
            return None
        if stripped in board.legal_moves:
            return stripped
        return None

    piece = board.piece_at(move.from_square)
    if piece is None or piece.piece_type != chess.PAWN:
        return None
    if chess.square_rank(move.to_square) not in (0, 7):
        return None
    for letter, piece_type in PROMOTION_PIECES.items():
        candidate = chess.Move(move.from_square, move.to_square, promotion=piece_type)
        if candidate in board.legal_moves:
            return candidate
    return None


def legal_destinations(board: chess.Board, color: chess.Color | None = None) -> dict[str, list[str]]:
    """Legal target squares, keyed by origin square.

    Refusing to answer while the other side is to move is the fix for the old
    false "illegal move" reports: the UI then has nothing to drag for the bot
    and the server never sees a bot move as a player move.
    """
    if board.is_game_over(claim_draw=True):
        return {}
    if color is not None and board.turn != color:
        return {}
    out: dict[str, list[str]] = {}
    for move in board.legal_moves:
        origin = chess.square_name(move.from_square)
        target = chess.square_name(move.to_square)
        bucket = out.setdefault(origin, [])
        if target not in bucket:
            bucket.append(target)
    for targets in out.values():
        targets.sort()
    return out


def move_flags(board: chess.Board, move: chess.Move) -> dict[str, bool]:
    """Facts about a move, read from the position *before* it is played."""
    after = board.copy()
    after.push(move)
    return {
        "capture": board.is_capture(move),
        "en_passant": board.is_en_passant(move),
        "castle": board.is_castling(move),
        "promotion": move.promotion is not None,
        "check": after.is_check(),
        "mate": after.is_checkmate(),
        "game_over": after.is_game_over(claim_draw=True),
    }


def material_cp(board: chess.Board, color: chess.Color | None = None) -> int:
    """Material balance in centipawns (white positive when color is None)."""
    total = 0
    for piece in board.piece_map().values():
        value = PIECE_VALUE.get(piece.piece_type, 0)
        total += value if piece.color == chess.WHITE else -value
    if color is None:
        return total
    return total if color == chess.WHITE else -total


def is_sacrifice(board_after: chess.Board, to_square: chess.Square,
                 mover: chess.Color) -> bool:
    """Cheap brilliant-move heuristic: the moved piece is hanging for less.

    A real sacrifice search needs a deep line, which the review does not
    attempt.  This catches the common shape (piece offered to a cheaper
    attacker, not compensated by a defender of equal value) and is only used
    together with a healthy evaluation.
    """
    piece = board_after.piece_at(to_square)
    if piece is None or piece.piece_type == chess.KING:
        return False
    attackers = board_after.attackers(not mover, to_square)
    if not attackers:
        return False
    defenders = board_after.attackers(mover, to_square)
    cheapest = 0
    for square in attackers:
        attacker = board_after.piece_at(square)
        if attacker is None:
            continue
        cost = PIECE_VALUE.get(attacker.piece_type, 0)
        if cheapest == 0 or cost < cheapest:
            cheapest = cost
    value = PIECE_VALUE.get(piece.piece_type, 0)
    if defenders and cheapest >= value:
        return False
    return value >= 300


def king_square(board: chess.Board, color: chess.Color) -> chess.Square | None:
    for square, piece in board.piece_map().items():
        if piece.piece_type == chess.KING and piece.color == color:
            return square
    return None
