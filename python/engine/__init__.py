"""
Date created: Jun 14
Author: Kane Weng

Core chess engine: board representation, evaluation, search, transposition table.
Re-exports the most commonly used names for convenience.
"""

from .board import STARTPOS_FEN, CBoard, Color, PieceType, Square
from .evaluate import BaseEvaluate, ComplexEvaluate, MediumEvaluate, SimpleEvaluate
from .search import Search
from .transposition import TranspositionTable, TTFlag

__all__ = [
    "CBoard",
    "Color",
    "PieceType",
    "Square",
    "STARTPOS_FEN",
    "BaseEvaluate",
    "SimpleEvaluate",
    "MediumEvaluate",
    "ComplexEvaluate",
    "Search",
    "TranspositionTable",
    "TTFlag",
]
