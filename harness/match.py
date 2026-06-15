"""
Date created: Jun 14
Author: Kane Weng

Self-contained UCI match runner.

Launches two UCI engines as subprocesses and plays a series of games, alternating
colours each game and seeding openings from an EPD suite for positional variety.
Eschess's own CBoard acts as the referee (legality, checkmate, stalemate, 50-move,
threefold repetition, insufficient material). Results are written as a PGN that
harness/elo.py (or Ordo / BayesElo) can rate.

Example => Eschess vs a 1320-rated Stockfish, 100 games at 100ms/move:

    python harness/match.py \
        --engine1 "python3 uci.py" --name1 Eschess \
        --engine2 "stockfish" --name2 SF-1320 \
        --opt2 UCI_LimitStrength=true --opt2 UCI_Elo=1320 \
        --games 100 --movetime 100 \
        --openings harness/openings.epd --pgn results.pgn
"""

import argparse
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "python"))

from engine.board import CBoard, Color, PieceType, STARTPOS_FEN, bits_to_squares  # noqa: E402
from uci import move_to_uci, uci_to_move                                          # noqa: E402


class UCIProcess:
    """Thin wrapper around a UCI engine subprocess."""

    def __init__(self, command: str, name: str, options: dict[str, str]):
        self.name = name
        # Starts the engine
        self._proc = subprocess.Popen(
            command, shell=True, text=True, bufsize=1,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        )
        # UCI Handshake protocol
        self._send("uci")
        self._wait_for("uciok")
        for key, value in options.items():
            self._send(f"setoption name {key} value {value}")
        self.isready()

    def _send(self, line: str) -> None:
        assert self._proc.stdin is not None
        self._proc.stdin.write(line + "\n")
        self._proc.stdin.flush()

    def _wait_for(self, token: str) -> None:
        assert self._proc.stdout is not None
        for line in self._proc.stdout:
            if line.strip() == token:
                return
        raise RuntimeError(f"{self.name}: engine closed before '{token}'")

    def isready(self) -> None:
        self._send("isready")
        self._wait_for("readyok")

    def new_game(self) -> None:
        self._send("ucinewgame")
        self.isready()

    def bestmove(self, start_fen: str, moves: list[str], go: str) -> str | None:
        """Set the position, issue "go", and return the engine's bestmove token."""
        pos = "startpos" if start_fen == STARTPOS_FEN else f"fen {start_fen}"
        suffix = f" moves {' '.join(moves)}" if moves else ""
        self._send(f"position {pos}{suffix}")
        self._send(go)
        assert self._proc.stdout is not None
        for line in self._proc.stdout:
            if line.startswith("bestmove"):
                token = line.split()[1]
                return None if token == "0000" else token
        return None

    def close(self) -> None:
        try:
            self._send("quit")
            self._proc.wait(timeout=5)
        except Exception:
            self._proc.kill()


# ── Referee: terminal-state detection ────────────────────────────────────────

def _insufficient_material(board: CBoard) -> bool:
    """K vs K, K+minor vs K, and K+B vs K+B (same-colour bishops) are draws."""
    if board.pieces[PieceType.PAWN] or board.pieces[PieceType.ROOK] or board.pieces[PieceType.QUEEN]:
        return False
    knights = bin(board.pieces[PieceType.KNIGHT]).count("1")
    bishops_bb = board.pieces[PieceType.BISHOP]
    bishops = bin(bishops_bb).count("1")
    if knights == 0 and bishops == 0:
        return True                       # K vs K
    if knights + bishops == 1:
        return True                       # lone minor
    if knights == 0 and bishops == 2:     # one bishop each → same colour squares?
        squares = list(bits_to_squares(bishops_bb))
        light = [(sq // 8 + sq % 8) % 2 for sq in squares]
        return light[0] == light[1]
    return False


def game_result(board: CBoard, rep_counts: dict[int, int]) -> str | None:
    """Return '1-0' / '0-1' / '1/2-1/2' if the game is over, else None."""
    if not board.get_all_legal_moves():
        if board.is_in_check(board.turn):
            return "0-1" if board.turn == Color.WHITE else "1-0"   # checkmated
        return "1/2-1/2"                                           # stalemate
    if board.halfmove_clock >= 100:
        return "1/2-1/2"                                           # 50-move rule
    if rep_counts.get(board.zobrist_key, 0) >= 3:
        return "1/2-1/2"                                           # threefold
    if _insufficient_material(board):
        return "1/2-1/2"
    return None


# ── One game ─────────────────────────────────────────────────────────────────

def play_game(white: UCIProcess, black: UCIProcess, opening_fen: str,
              go_command: str, max_plies: int) -> tuple[str, list[str]]:
    """Play a single game; return (result, uci_move_list)."""
    board = CBoard.from_fen(opening_fen)
    white.new_game()
    black.new_game()

    rep_counts: dict[int, int] = {board.zobrist_key: 1}
    moves: list[str] = []

    result = game_result(board, rep_counts)
    while result is None and len(moves) < max_plies:
        engine = white if board.turn == Color.WHITE else black
        token = engine.bestmove(opening_fen, moves, go_command)
        if token is None:
            # No move returned → loss for the side to move.
            return ("0-1" if board.turn == Color.WHITE else "1-0"), moves

        from_square, to_square, promotion = uci_to_move(token)
        if not (board.get_legal_moves(from_square) & (1 << to_square)):
            # Illegal move → forfeit by the offending engine.
            return ("0-1" if board.turn == Color.WHITE else "1-0"), moves

        board.make_move(from_square, to_square, promotion)
        moves.append(token)
        rep_counts[board.zobrist_key] = rep_counts.get(board.zobrist_key, 0) + 1
        result = game_result(board, rep_counts)

    return (result or "1/2-1/2"), moves


# ── PGN output ────────────────────────────────────────────────────────────────

def write_pgn(fh, rnd: int, white_name: str, black_name: str,
              opening_fen: str, result: str, moves: list[str]) -> None:
    fh.write(f'[Event "Eschess harness match"]\n')
    fh.write(f'[Round "{rnd}"]\n')
    fh.write(f'[White "{white_name}"]\n')
    fh.write(f'[Black "{black_name}"]\n')
    fh.write(f'[Result "{result}"]\n')
    if opening_fen != STARTPOS_FEN:
        fh.write('[SetUp "1"]\n')
        fh.write(f'[FEN "{opening_fen}"]\n')
    fh.write("\n")
    # Moves in UCI coordinate notation
    fh.write(" ".join(moves))
    fh.write(f" {result}\n\n")
    fh.flush()


# ── Openings ──────────────────────────────────────────────────────────────────

def load_openings(path: str | None) -> list[str]:
    if path is None:
        return [STARTPOS_FEN]
    fens: list[str] = []
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # EPD: first four fields are the position; append clocks to make a full FEN.
        fields = line.split()
        fen = " ".join(fields[:4]) + " 0 1" if len(fields) >= 4 else line
        fens.append(fen)
    return fens or [STARTPOS_FEN]


# ── Driver ─────────────────────────────────────────────────────────────────────

def _parse_opts(pairs: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for pair in pairs or []:
        key, _, value = pair.partition("=")
        out[key.strip()] = value.strip()
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Run a UCI engine-vs-engine match.")
    ap.add_argument("--engine1", required=True, help="shell command to launch engine 1")
    ap.add_argument("--engine2", required=True, help="shell command to launch engine 2")
    ap.add_argument("--name1", default="Engine1")
    ap.add_argument("--name2", default="Engine2")
    ap.add_argument("--opt1", action="append", default=[], help="UCI option NAME=VALUE for engine 1")
    ap.add_argument("--opt2", action="append", default=[], help="UCI option NAME=VALUE for engine 2")
    ap.add_argument("--games", type=int, default=100)
    ap.add_argument("--movetime", type=int, default=100, help="ms per move (fixed time)")
    ap.add_argument("--max-plies", type=int, default=400, help="adjudicate a draw past this many plies")
    ap.add_argument("--openings", default=None, help="EPD/FEN opening suite (one per line)")
    ap.add_argument("--pgn", default="results.pgn")
    ap.add_argument("--concurrency", type=int, default=1, help="number of games to play in parallel")
    args = ap.parse_args()

    openings = load_openings(args.openings)
    go_command = f"go movetime {args.movetime}"
    opts1, opts2 = _parse_opts(args.opt1), _parse_opts(args.opt2)

    # One queue of game indices; each worker owns its own engine pair and drains it.
    work_q: "queue.Queue[int]" = queue.Queue()
    for game_idx in range(args.games):
        work_q.put(game_idx)

    # Shared scoreboard (from engine 1's perspective), guarded by a lock together
    # with the PGN handle since games finish out of order across workers.
    stats = {"wins": 0, "losses": 0, "draws": 0, "done": 0}
    lock = threading.Lock()
    started = time.time()
    pgn = open(args.pgn, "w")

    def worker() -> None:
        e1 = UCIProcess(args.engine1, args.name1, opts1)
        e2 = UCIProcess(args.engine2, args.name2, opts2)
        try:
            while True:
                try:
                    game_idx = work_q.get_nowait()
                except queue.Empty:
                    break
                opening = openings[(game_idx // 2) % len(openings)]  # same opening, both colours
                e1_is_white = (game_idx % 2 == 0)
                white, black = (e1, e2) if e1_is_white else (e2, e1)

                result, moves = play_game(white, black, opening, go_command, args.max_plies)

                with lock:
                    if result == "1/2-1/2":
                        stats["draws"] += 1
                    elif (result == "1-0") == e1_is_white:
                        stats["wins"] += 1
                    else:
                        stats["losses"] += 1
                    stats["done"] += 1
                    write_pgn(pgn, game_idx + 1, white.name, black.name, opening, result, moves)
                    score = stats["wins"] + 0.5 * stats["draws"]
                    print(f"[{stats['done']}/{args.games}] {white.name} vs {black.name}: {result}  "
                          f"| {args.name1} +{stats['wins']} -{stats['losses']} ={stats['draws']}  "
                          f"({score}/{stats['done']})", flush=True)
        finally:
            e1.close()
            e2.close()

    num_workers = max(1, min(args.concurrency, args.games))
    threads = [threading.Thread(target=worker) for _ in range(num_workers)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    pgn.close()

    n = args.games
    score = stats["wins"] + 0.5 * stats["draws"]
    print(f"\nFinished {n} games in {time.time() - started:.1f}s  (concurrency {num_workers})")
    print(f"{args.name1}: +{stats['wins']} -{stats['losses']} ={stats['draws']}  "
          f"score {score}/{n} = {score / n:.1%}")
    print(f"PGN written to {args.pgn}  ->  rate it with: python harness/elo.py {args.pgn}")


if __name__ == "__main__":
    main()
