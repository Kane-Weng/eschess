"""
Date created: Jun 14
Author: Kane Weng

Encoding between the chess board and the tensors a network consumes/produces.

  board_to_planes : CBoard -> float32 array of shape (INPUT_PLANES, 8, 8)
  move_to_index   : (from_square, to_square) -> flat policy index in [0, 4096)
  index_to_move   : flat policy index -> (from_square, to_square)
  legal_policy_mask : CBoard -> float32 array of shape (POLICY_SIZE,)

Both nets read the same plane stack. The policy head uses a simple from-to
scheme: 64 source squares times 64 destination squares. Promotions collapse to
queen here (the most common case); distinguishing under-promotions is a future
extension that would widen POLICY_SIZE.
"""

import numpy as np

from engine.board import CR_BK, CR_BQ, CR_WK, CR_WQ, CBoard, Color, PieceType

# -- Plane layout ------------------------------------------------------------
# 12 piece planes (6 piece types per colour), and 6 auxiliary state planes.
_PIECE_ORDER = [
    PieceType.PAWN,
    PieceType.KNIGHT,
    PieceType.BISHOP,
    PieceType.ROOK,
    PieceType.QUEEN,
    PieceType.KING,
]
_NUM_PIECE_PLANES = 12
_PLANE_STM = 12  # side to move (all ones when White to move)
_PLANE_CASTLE = 13  # four planes: WK, WQ, BK, BQ
_PLANE_EP = 17  # en passant target square (single one-hot square)
INPUT_PLANES = 18

_CASTLE_BITS = [CR_WK, CR_WQ, CR_BK, CR_BQ]

# -- Policy layout -----------------------------------------------------------
POLICY_SIZE = 64 * 64  # 4096 from-to combinations


def _piece_plane_index(color: Color, piece_type: PieceType) -> int:
    """Row of the piece-plane block for a (color, type) pair."""
    return color.value * 6 + _PIECE_ORDER.index(piece_type)


def _fill_plane(plane: np.ndarray, bits: int) -> None:
    """Set every square present in a bitboard to 1.0 on an 8x8 plane."""
    for square in CBoard.bits_to_squares(bits):
        rank_idx, file_idx = CBoard.get_rank_idx(square), CBoard.get_file_idx(square)
        plane[rank_idx, file_idx] = 1.0


def _piece_planes(board: CBoard, planes: np.ndarray) -> None:
    for color in Color:
        for piece_type in _PIECE_ORDER:
            row = _piece_plane_index(color, piece_type)
            _fill_plane(planes[row], board.get_specific_pieces(color, piece_type))


def _aux_planes(board: CBoard, planes: np.ndarray) -> None:
    if board.turn == Color.WHITE:
        planes[_PLANE_STM, :, :] = 1.0
    for offset, bit in enumerate(_CASTLE_BITS):
        if board.castling_rights & bit:
            planes[_PLANE_CASTLE + offset, :, :] = 1.0
    if board.en_passant_square is not None:
        square = board.en_passant_square
        planes[_PLANE_EP, CBoard.get_rank_idx(square), CBoard.get_file_idx(square)] = 1.0


def board_to_planes(board: CBoard) -> np.ndarray:
    """Encode a position as an (INPUT_PLANES, 8, 8) float32 tensor."""
    planes = np.zeros((INPUT_PLANES, 8, 8), dtype=np.float32)
    _piece_planes(board, planes)
    _aux_planes(board, planes)
    return planes


# -- Move encoding -----------------------------------------------------------


def move_to_index(from_square: int, to_square: int) -> int:
    """Pack a (from, to) move into a flat policy index."""
    return from_square * 64 + to_square


def index_to_move(index: int) -> tuple[int, int]:
    """Unpack a flat policy index into (from_square, to_square)."""
    return index // 64, index % 64


def legal_policy_mask(board: CBoard) -> np.ndarray:
    """1.0 at every legal from-to index for the side to move, 0.0 elsewhere."""
    mask = np.zeros(POLICY_SIZE, dtype=np.float32)
    for from_square, legal_bits in board.get_all_legal_moves():
        for to_square in CBoard.bits_to_squares(legal_bits):
            mask[move_to_index(from_square, to_square)] = 1.0
    return mask
