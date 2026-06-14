"""
Date created: Jun 14
Author: Kane Weng

Core chess engine: board representation, evaluation, search, transposition table.
Re-exports the most commonly used names for convenience.
"""

from .board import CBoard, Color, PieceType, Square, STARTPOS_FEN
from .evaluate import BaseEvaluate, SimpleEvaluate, MediumEvaluate, ComplexEvaluate
from .search import Search
from .transposition import TranspositionTable, TTFlag

__all__ = [
    "CBoard", "Color", "PieceType", "Square", "STARTPOS_FEN",
    "BaseEvaluate", "SimpleEvaluate", "MediumEvaluate", "ComplexEvaluate",
    "Search", "TranspositionTable", "TTFlag",
]
