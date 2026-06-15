"""
Date created: Jun 15
Author: Kane Weng

Self-play game generation for the reinforcement-learning loop. Each move is
chosen by MCTS; the resulting visit distribution becomes the policy target and
the final game result becomes the value target for every position in the game.

  game_outcome : terminal result (White perspective) or None if the game is live.
  play_game    : run one MCTS-driven game, returning training samples.

The board itself does not adjudicate draws, so this module layers the standard
draw rules on top of checkmate/stalemate: the fifty-move clock, threefold
repetition (tracked by Zobrist key), and trivially insufficient material. A move
cap adjudicates the rare unfinished game as a draw so generation always halts.

Value targets follow the existing ValueNet convention: White's perspective in
{+1, 0, -1}. Policy targets are stored sparsely as (policy_index, probability)
pairs over the legal moves MCTS actually visited.
"""

from dataclasses import dataclass

import numpy as np

from engine.board import CBoard, Color, PieceType
from .encoding import board_to_planes, move_to_index
from .mcts import MCTS, select_move, visit_policy

_DRAW_PIECES = (PieceType.PAWN, PieceType.ROOK, PieceType.QUEEN)


@dataclass
class SelfPlaySample:
    """One training example produced by self-play."""
    planes: np.ndarray                       # (INPUT_PLANES, 8, 8) float32
    policy_target: list[tuple[int, float]]   # sparse (policy_index, probability)
    value: float                             # game result, White's perspective


def _popcount(bits: int) -> int:
    return bits.bit_count()


def _insufficient_material(board: CBoard) -> bool:
    """True for the obvious draws: bare kings or a lone minor piece."""
    for piece_type in _DRAW_PIECES:
        if board.get_specific_pieces(Color.WHITE, piece_type) or \
           board.get_specific_pieces(Color.BLACK, piece_type):
            return False
    minors = 0
    for piece_type in (PieceType.KNIGHT, PieceType.BISHOP):
        minors += _popcount(board.get_specific_pieces(Color.WHITE, piece_type))
        minors += _popcount(board.get_specific_pieces(Color.BLACK, piece_type))
    return minors <= 1


def game_outcome(board: CBoard, rep_counts: dict[int, int]) -> float | None:
    """White-perspective result (+1/0/-1), or None while the game continues."""
    if not board.get_all_legal_moves():
        if board.is_in_check(board.turn):
            return -1.0 if board.turn == Color.WHITE else 1.0   # side to move is mated
        return 0.0                                              # stalemate
    if board.halfmove_clock >= 100:
        return 0.0                                              # fifty-move rule
    if rep_counts.get(board.zobrist_key, 0) >= 3:
        return 0.0                                              # threefold repetition
    if _insufficient_material(board):
        return 0.0
    return None


def play_game(mcts: MCTS, max_moves: int = 200, temp_moves: int = 30,
              temperature: float = 1.0) -> list[SelfPlaySample]:
    """Play one self-play game and return its training samples."""
    board = CBoard()
    rep_counts: dict[int, int] = {board.zobrist_key: 1}
    records: list[tuple[np.ndarray, list[tuple[int, float]]]] = []

    move_num = 0
    while True:
        outcome = game_outcome(board, rep_counts)
        if outcome is not None:
            result = outcome
            break
        if move_num >= max_moves:
            result = 0.0   # adjudicate an over-long game as a draw
            break

        visit_counts = mcts.run(board, add_noise=True)
        planes = board_to_planes(board)
        target = [(move_to_index(f, t), p) for (f, t), p in visit_policy(visit_counts).items()]
        records.append((planes, target))

        temp = temperature if move_num < temp_moves else 0.0
        from_square, to_square = select_move(visit_counts, temp)
        promotion = PieceType.QUEEN if board.needs_promotion(from_square, to_square) else None
        board.make_move(from_square, to_square, promotion)
        rep_counts[board.zobrist_key] = rep_counts.get(board.zobrist_key, 0) + 1
        move_num += 1

    return [SelfPlaySample(planes, target, result) for planes, target in records]
