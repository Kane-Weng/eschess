"""
Date created: Jun 15
Author: Kane Weng

PUCT Monte Carlo Tree Search, AlphaZero-style. The policy network supplies the
prior over moves at each expanded node; the value network scores leaf positions.
Search runs on a single mutated CBoard via make_move/unmake_move (moves are made
on the way down and unmade on the way back up, so the board is left untouched).

  MCTSNode : one position in the tree (prior P, visit count N, value sum W).
  MCTS     : run(board) -> {(from, to): visit_count} root visit distribution.

Sign convention: every node's value is stored from the perspective of the side
to move at that node. A child is the opponent's turn, so a parent reads the
child's mean value negated. Leaf values are likewise side-to-move relative:
the value net's White-perspective output is flipped when Black is to move, and a
checkmate is -1 for the side that has no move.

Promotions follow the policy head's queen-only encoding: a move is keyed by
(from, to) and resolved to a queen promotion at make time when it reaches the
back rank.
"""

import math

import numpy as np

from engine.board import CBoard, Color, PieceType
from .inference import policy_priors, value_estimate
from .network import PolicyNet, ValueNet

# Move identity within the tree: (from_square, to_square). The policy head does
# not distinguish promotion pieces, so neither does the search.
MoveKey = tuple[int, int]


class MCTSNode:
    """A single node in the search tree."""

    __slots__ = ("prior", "visit_count", "value_sum", "children", "is_expanded")

    def __init__(self, prior: float):
        self.prior       = prior
        self.visit_count = 0
        self.value_sum   = 0.0
        self.children: dict[MoveKey, "MCTSNode"] = {}
        self.is_expanded = False

    def mean_value(self) -> float:
        """Average value from this node's side-to-move perspective."""
        return self.value_sum / self.visit_count if self.visit_count else 0.0


def _resolve_promotion(board: CBoard, from_square: int, to_square: int) -> PieceType | None:
    """Queen promotion when the move reaches the back rank, else None."""
    return PieceType.QUEEN if board.needs_promotion(from_square, to_square) else None


class MCTS:
    """AlphaZero-style PUCT search guided by the policy and value networks."""

    def __init__(self, policy_net: PolicyNet, value_net: ValueNet, device: str = "cpu",
                 n_simulations: int = 100, c_puct: float = 1.5,
                 dirichlet_alpha: float = 0.3, noise_frac: float = 0.25):
        self.policy_net      = policy_net
        self.value_net       = value_net
        self.device          = device
        self.n_simulations   = n_simulations
        self.c_puct          = c_puct
        self.dirichlet_alpha = dirichlet_alpha
        self.noise_frac      = noise_frac

    # -- Public API ----------------------------------------------------------

    def run(self, board: CBoard, add_noise: bool = True) -> dict[MoveKey, int]:
        """Run the simulations and return root child visit counts."""
        root = MCTSNode(prior=1.0)
        self._expand(root, board, add_noise=add_noise)

        for _ in range(self.n_simulations):
            node = root
            path = [root]
            # Selection: walk down, making moves, until an unexpanded node.
            while node.is_expanded and node.children:
                move_key, node = self._select_child(node)
                from_square, to_square = move_key
                board.make_move(from_square, to_square,
                                _resolve_promotion(board, from_square, to_square))
                path.append(node)

            value = self._evaluate_leaf(node, board)
            self._backup(path, value)

            for _ in range(len(path) - 1):  # restore the board
                board.unmake_move()

        return {move_key: child.visit_count for move_key, child in root.children.items()}

    # -- Search internals ----------------------------------------------------

    def _select_child(self, node: MCTSNode) -> tuple[MoveKey, MCTSNode]:
        """Pick the child maximising Q + U (PUCT)."""
        sqrt_total = math.sqrt(node.visit_count)
        best_score, best = -float("inf"), None
        for move_key, child in node.children.items():
            # child.mean_value() is the opponent's perspective, so negate it.
            q = -child.mean_value()
            u = self.c_puct * child.prior * sqrt_total / (1 + child.visit_count)
            score = q + u
            if score > best_score:
                best_score, best = score, (move_key, child)
        return best

    def _evaluate_leaf(self, node: MCTSNode, board: CBoard) -> float:
        """Value of a leaf from its side-to-move perspective (and expand it)."""
        terminal = _terminal_value(board)
        if terminal is not None:
            return terminal
        self._expand(node, board)
        return self._leaf_value(board)

    def _expand(self, node: MCTSNode, board: CBoard, add_noise: bool = False) -> None:
        priors = policy_priors(self.policy_net, board, self.device)
        if add_noise and priors:
            priors = self._apply_noise(priors)
        for move_key, prob in priors.items():
            node.children[move_key] = MCTSNode(prior=prob)
        node.is_expanded = True

    def _apply_noise(self, priors: dict[MoveKey, float]) -> dict[MoveKey, float]:
        """Mix Dirichlet noise into the root priors for exploration."""
        moves = list(priors)
        noise = np.random.dirichlet([self.dirichlet_alpha] * len(moves))
        frac = self.noise_frac
        return {m: (1 - frac) * priors[m] + frac * float(n) for m, n in zip(moves, noise)}

    def _leaf_value(self, board: CBoard) -> float:
        """Value-net estimate converted to the side-to-move perspective."""
        white_value = value_estimate(self.value_net, board, self.device)
        return white_value if board.turn == Color.WHITE else -white_value

    @staticmethod
    def _backup(path: list[MCTSNode], value: float) -> None:
        """Propagate the leaf value up the path, flipping sign each ply."""
        for node in reversed(path):
            node.visit_count += 1
            node.value_sum   += value
            value = -value


def _terminal_value(board: CBoard) -> float | None:
    """Game-over value from the side-to-move perspective, or None if ongoing.

    Only the no-legal-move cases are checked here (checkmate / stalemate); the
    self-play loop layers on the repetition and move-clock draws.
    """
    if board.get_all_legal_moves():
        return None
    return -1.0 if board.is_in_check(board.turn) else 0.0


# -- Move selection from visit counts ----------------------------------------

def visit_policy(visit_counts: dict[MoveKey, int]) -> dict[MoveKey, float]:
    """Normalise visit counts into a probability distribution (training target)."""
    total = sum(visit_counts.values())
    if total == 0:
        return {}
    return {move_key: count / total for move_key, count in visit_counts.items()}


def select_move(visit_counts: dict[MoveKey, int], temperature: float = 1.0) -> MoveKey:
    """Pick a move from the visit counts: greedy at temperature 0, else sampled."""
    moves = list(visit_counts)
    counts = np.array([visit_counts[m] for m in moves], dtype=np.float64)
    if temperature <= 1e-6:
        return moves[int(counts.argmax())]
    weights = counts ** (1.0 / temperature)
    weights /= weights.sum()
    return moves[int(np.random.choice(len(moves), p=weights))]
