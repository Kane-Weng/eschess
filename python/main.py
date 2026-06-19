"""
Date created: Jun 13
Author: Kane Weng

Main execution file for a chess game using pygame.

Interactive sandbox features:
- A right-hand Engine settings panel (change lang / search / eval / depth live)
- An Engine performance panel (nodes / NPS / depth / think time)
- A left vertical eval bar (Stockfish-backed, else the engine's own score)
- A scrollable move list below the board with undo / redo,
- Collapsible captured-tray and move sections, and
- Optional visualization tools
"""

import argparse
import copy
import math
import sys
import threading
from pathlib import Path

import pygame

import engine_backend
import eval_probe
import sidebar
from engine.board import CBoard, Color, PieceType
from engine_backend import make_engine

ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"

SQUARE_SIZE = 80
PIECE_SIZE = int(SQUARE_SIZE * 0.8)
BOARD_PX = SQUARE_SIZE * 8
STATUS_H = 36

# Layout: [eval bar][board][right menu]; status bar + scrollable move list sit
# below the board, spanning the eval bar + board width.
EVAL_BAR_W = 26
BOARD_ORIGIN_X = EVAL_BAR_W
MENU_W = 300
MENU_X = BOARD_ORIGIN_X + BOARD_PX
WINDOW_W = EVAL_BAR_W + BOARD_PX + MENU_W
WINDOW_H = 880

MOVELIST_Y = BOARD_PX + STATUS_H  # top of the move-list strip under the board
MOVELIST_W = MENU_X  # spans eval bar + board

# Board-only span, used by the overlays that cover the board region.
WIDTH = BOARD_PX
HEIGHT = BOARD_PX + STATUS_H
FPS = 60

PLAYER_COLOR = Color.WHITE  
BOT_COLOR = Color.BLACK
BOT_DEPTH = 3
FLIPPED = False

LIGHT_SQ = pygame.Color(240, 217, 181)
DARK_SQ = pygame.Color(181, 136, 99)
HIGHLIGHT = (255, 255, 0, 140)  # yellow, semi-transparent
LAST_MOVE = (120, 190, 120, 130)  # green tint on the most recent move
DOT_COLOR = (0, 0, 0, 150)  # black dot, semi-transparent
CAPTURE_RG = (180, 0, 0, 120)  # red ring on capturable squares
STATUS_BG = (30, 30, 30, 220)
STATUS_TURN_BG = (40, 110, 55, 235)  # lit-up green when it's the player's turn
WINDOW_BG = (18, 18, 22)

# Search-path arrow colors (one per side; deliberately not black/white).
ARROW_BOT_SIDE = (235, 150, 40)  # side that moved first in the PV (the bot)
ARROW_PLAYER_SIDE = (60, 180, 210)
# Top-3 PV arrows, colored by rank: best / alternative / worst.
ARROW_RANK = [(70, 200, 90), (225, 185, 60), (215, 70, 70)]
DENSITY_COLOR = (255, 120, 40)  # density-cloud rings (single warm hue)

IMAGES: dict[tuple[Color, PieceType], pygame.Surface] = {}
SMALL_IMAGES: dict[tuple[Color, PieceType], pygame.Surface] = {}  # captured tray

PROMO_PIECES = [PieceType.QUEEN, PieceType.ROOK, PieceType.BISHOP, PieceType.KNIGHT]

# Material for the captured-tray advantage readout.
_START_COUNTS = {
    PieceType.PAWN: 8,
    PieceType.KNIGHT: 2,
    PieceType.BISHOP: 2,
    PieceType.ROOK: 2,
    PieceType.QUEEN: 1,
    PieceType.KING: 1,
}
_PIECE_VALUE = {
    PieceType.PAWN: 1,
    PieceType.KNIGHT: 3,
    PieceType.BISHOP: 3,
    PieceType.ROOK: 5,
    PieceType.QUEEN: 9,
    PieceType.KING: 0,
}


def load_assets():
    color_chars = {Color.WHITE: "w", Color.BLACK: "b"}
    piece_chars = {
        PieceType.PAWN: "pawn",
        PieceType.KNIGHT: "knight",
        PieceType.BISHOP: "bishop",
        PieceType.ROOK: "rook",
        PieceType.QUEEN: "queen",
        PieceType.KING: "king",
    }
    for color in Color:
        for piece in PieceType:
            filename = ASSETS_DIR / f"{color_chars[color]}_{piece_chars[piece]}_png_1024px.png"
            img = pygame.image.load(str(filename)).convert_alpha()
            IMAGES[(color, piece)] = pygame.transform.smoothscale(img, (PIECE_SIZE, PIECE_SIZE))
            SMALL_IMAGES[(color, piece)] = pygame.transform.smoothscale(img, (22, 22))


def sq_to_screen(sq: int) -> tuple[int, int]:
    """Top-left pixel of the square (board is offset right of the eval bar)."""
    file_idx = CBoard.get_file_idx(sq)
    rank_idx = CBoard.get_rank_idx(sq)
    if FLIPPED:
        return BOARD_ORIGIN_X + (7 - file_idx) * SQUARE_SIZE, rank_idx * SQUARE_SIZE
    return BOARD_ORIGIN_X + file_idx * SQUARE_SIZE, (7 - rank_idx) * SQUARE_SIZE


def sq_center(sq: int) -> tuple[int, int]:
    x, y = sq_to_screen(sq)
    return x + SQUARE_SIZE // 2, y + SQUARE_SIZE // 2


def screen_to_sq(x: int, y: int) -> int:
    col = (x - BOARD_ORIGIN_X) // SQUARE_SIZE
    row = y // SQUARE_SIZE
    if not (0 <= col <= 7 and 0 <= row <= 7):
        return -1
    file_idx = 7 - col if FLIPPED else col
    rank_idx = row if FLIPPED else 7 - row
    return CBoard.get_square_idx(rank_idx, file_idx)


def draw_board(screen: pygame.Surface, selected_sq: int | None, last_move: tuple[int, int] | None):
    for sq in range(64):
        file_idx = CBoard.get_file_idx(sq)
        rank_idx = CBoard.get_rank_idx(sq)
        color = LIGHT_SQ if (rank_idx + file_idx) % 2 == 0 else DARK_SQ
        x, y = sq_to_screen(sq)
        pygame.draw.rect(screen, color, (x, y, SQUARE_SIZE, SQUARE_SIZE))

    # Most-recent-move tint
    if last_move is not None:
        tint = pygame.Surface((SQUARE_SIZE, SQUARE_SIZE), pygame.SRCALPHA)
        tint.fill(LAST_MOVE)
        for sq in last_move:
            screen.blit(tint, sq_to_screen(sq))

    # Selection highlight
    if selected_sq is not None and selected_sq >= 0:
        hl = pygame.Surface((SQUARE_SIZE, SQUARE_SIZE), pygame.SRCALPHA)
        hl.fill(HIGHLIGHT)
        screen.blit(hl, sq_to_screen(selected_sq))


def draw_pieces(screen: pygame.Surface, board: CBoard):
    offset = (SQUARE_SIZE - PIECE_SIZE) // 2
    for color in Color:
        for piece in PieceType:
            mask = board.get_specific_pieces(color, piece)
            for sq in CBoard.bits_to_squares(mask):
                x, y = sq_to_screen(sq)
                screen.blit(IMAGES[(color, piece)], (x + offset, y + offset))


def draw_move_dots(screen: pygame.Surface, board: CBoard, legal_mask: int):
    """Draw a translucent dot (empty square) or ring (capture square) for each legal destination."""
    if not legal_mask:
        return
    occ = board.occupied()
    dot_surf = pygame.Surface((SQUARE_SIZE, SQUARE_SIZE), pygame.SRCALPHA)

    for sq in CBoard.bits_to_squares(legal_mask):
        x, y = sq_to_screen(sq)
        dot_surf.fill((0, 0, 0, 0))
        if occ & (1 << sq):
            pygame.draw.circle(
                dot_surf, CAPTURE_RG, (SQUARE_SIZE // 2, SQUARE_SIZE // 2), SQUARE_SIZE // 2, 6
            )
        else:
            pygame.draw.circle(
                dot_surf, DOT_COLOR, (SQUARE_SIZE // 2, SQUARE_SIZE // 2), SQUARE_SIZE // 7
            )
        screen.blit(dot_surf, (x, y))


def _draw_arrow(surface, start, end, color, width=7, elbow=None):
    """Arrow from start to end on an alpha surface (color is RGBA)"""
    pts = [start, elbow, end] if elbow is not None else [start, end]
    tail, tip = pts[-2], pts[-1]
    dx, dy = tip[0] - tail[0], tip[1] - tail[1]
    dist = math.hypot(dx, dy)
    if dist < 1:
        return
    ux, uy = dx / dist, dy / dist
    head_len, head_w = 20, 7 + width
    base = (tip[0] - ux * head_len, tip[1] - uy * head_len)
    # draw the shaft up to where the head begins
    pygame.draw.lines(surface, color, False, pts[:-1] + [base], width)
    perp = (-uy, ux)
    left = (base[0] + perp[0] * head_w, base[1] + perp[1] * head_w)
    right = (base[0] - perp[0] * head_w, base[1] - perp[1] * head_w)
    pygame.draw.polygon(surface, color, [tip, left, right])


def _knight_elbow(from_sq: int, to_sq: int):
    """Elbow pixel for a knight L-arrow. The long (2-square) leg is drawn
    first, then the short (1-square) turn."""
    df = CBoard.get_file_idx(to_sq) - CBoard.get_file_idx(from_sq)
    dr = CBoard.get_rank_idx(to_sq) - CBoard.get_rank_idx(from_sq)
    if {abs(df), abs(dr)} != {1, 2}:
        return None
    sx, sy = sq_center(from_sq)
    ex, ey = sq_center(to_sq)
    # bend so the longer leg (the axis with distance 2) is travelled first
    return (ex, sy) if abs(df) == 2 else (sx, ey)


def draw_search_arrows(screen: pygame.Surface, pv: list):
    """Draw the engine's principal variation as arrows: one color per side, with
    deeper plies drawn fainter. PV ply 0 is the side that searched (the bot).
    The first two plies get thicker shafts; knight moves bend in an L."""
    if not pv:
        return
    overlay = pygame.Surface((MENU_X, BOARD_PX), pygame.SRCALPHA)
    for i, move in enumerate(pv):
        base = ARROW_BOT_SIDE if i % 2 == 0 else ARROW_PLAYER_SIDE
        alpha = max(45, 230 - i * 26)
        width = 11 if i < 2 else 7
        _draw_arrow(
            overlay,
            sq_center(move[0]),
            sq_center(move[1]),
            (*base, alpha),
            width=width,
            elbow=_knight_elbow(move[0], move[1]),
        )
    screen.blit(overlay, (0, 0))


def _cp_label(score_pawns: float, stm_white: bool) -> str:
    """Centipawns from the moving side's POV, e.g. '+120' / '-340' / 'M'."""
    stm = score_pawns if stm_white else -score_pawns
    if abs(stm) >= 999:
        return "M+" if stm > 0 else "M-"
    return f"{int(round(stm * 100)):+d}"


def draw_top3_arrows(screen: pygame.Surface, multipv: list, stm_white: bool):
    """The engine's top-3 root moves as rank-colored arrows (green=best, gold=alt,
    red=worst) with a cp label; each move's response chain is drawn thin/faint."""
    if not multipv:
        return
    overlay = pygame.Surface((MENU_X, BOARD_PX), pygame.SRCALPHA)
    labels: list[tuple[tuple[int, int], str, tuple]] = []
    for rank, entry in enumerate(multipv[:3]):
        color = ARROW_RANK[rank]
        pv = entry.get("pv") or ([entry["move"]] if entry.get("move") else [])
        if not pv:
            continue
        # faint response chain first (so the bold root move draws on top)
        for j, move in enumerate(pv[1:4], start=1):
            _draw_arrow(
                overlay,
                sq_center(move[0]),
                sq_center(move[1]),
                (*color, max(35, 120 - j * 25)),
                width=4,
                elbow=_knight_elbow(move[0], move[1]),
            )
        root = pv[0]
        _draw_arrow(
            overlay,
            sq_center(root[0]),
            sq_center(root[1]),
            (*color, 235),
            width=11,
            elbow=_knight_elbow(root[0], root[1]),
        )
        if entry.get("score") is not None:
            labels.append((sq_center(root[1]), _cp_label(entry["score"], stm_white), color))
    screen.blit(overlay, (0, 0))

    font = pygame.font.SysFont(None, 24)
    font.set_bold(True)
    for (cx, cy), text, color in labels:
        chip = font.render(text, True, (15, 15, 15))
        rect = chip.get_rect(center=(cx, cy - SQUARE_SIZE // 2 + 12))
        pygame.draw.rect(screen, color, rect.inflate(8, 4), border_radius=4)
        screen.blit(chip, rect)


def draw_density_cloud(screen: pygame.Surface, effort: dict):
    """Translucent rings on each candidate's destination square, sized/opaque by
    how many nodes the engine spent in that move's subtree (tactical friction)."""
    if not effort:
        return
    overlay = pygame.Surface((MENU_X, BOARD_PX), pygame.SRCALPHA)
    # combine effort per destination square (several moves can target one square)
    by_square: dict[int, int] = {}
    for move, nodes in effort.items():
        by_square[move[1]] = by_square.get(move[1], 0) + nodes
    peak = max(by_square.values()) or 1
    for sq, nodes in by_square.items():
        norm = max(0.0, min(1.0, nodes / peak))
        cx, cy = sq_center(sq)
        radius = int(12 + norm * (SQUARE_SIZE // 2 - 6))
        alpha = min(255, int(40 + norm * 150))
        pygame.draw.circle(overlay, (*DENSITY_COLOR, alpha), (cx, cy), radius)
        pygame.draw.circle(overlay, (*DENSITY_COLOR, min(255, alpha + 60)), (cx, cy), radius, 3)
    screen.blit(overlay, (0, 0))


def draw_promotion_picker(
    screen: pygame.Surface, color: Color
) -> list[tuple[pygame.Rect, PieceType]]:
    """Draw the promotion picker overlay and return clickable rects."""
    overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, 160))
    screen.blit(overlay, (BOARD_ORIGIN_X, 0))

    num = len(PROMO_PIECES)
    box_w = SQUARE_SIZE + 20
    box_h = SQUARE_SIZE + 20
    total_w = num * box_w + (num - 1) * 10
    start_x = BOARD_ORIGIN_X + (WIDTH - total_w) // 2
    y = (HEIGHT - box_h) // 2

    rects: list[tuple[pygame.Rect, PieceType]] = []
    font = pygame.font.SysFont(None, 22)
    labels = {
        PieceType.QUEEN: "Queen",
        PieceType.ROOK: "Rook",
        PieceType.BISHOP: "Bishop",
        PieceType.KNIGHT: "Knight",
    }

    for i, pt in enumerate(PROMO_PIECES):
        x = start_x + i * (box_w + 10)
        rect = pygame.Rect(x, y, box_w, box_h)
        pygame.draw.rect(screen, (220, 200, 150), rect, border_radius=8)
        pygame.draw.rect(screen, (80, 60, 30), rect, 2, border_radius=8)
        img_x = x + (box_w - PIECE_SIZE) // 2
        img_y = y + 4
        screen.blit(IMAGES[(color, pt)], (img_x, img_y))
        label = font.render(labels[pt], True, (40, 20, 0))
        screen.blit(label, (x + (box_w - label.get_width()) // 2, y + box_h - 18))
        rects.append((rect, pt))

    return rects


def draw_game_over(screen: pygame.Surface, board: CBoard):
    overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, 160))
    screen.blit(overlay, (BOARD_ORIGIN_X, 0))

    font_big = pygame.font.SysFont(None, 72)
    font_sm = pygame.font.SysFont(None, 36)

    if board.winner is None:
        msg = "Stalemate - Draw"
    elif board.winner == Color.WHITE:
        msg = "White Wins!"
    else:
        msg = "Black Wins!"

    cx = BOARD_ORIGIN_X + WIDTH // 2
    text = font_big.render(msg, True, (255, 255, 255))
    sub = font_sm.render("Press R to restart", True, (200, 200, 200))
    screen.blit(text, text.get_rect(center=(cx, HEIGHT // 2 - 24)))
    screen.blit(sub, sub.get_rect(center=(cx, HEIGHT // 2 + 36)))


def draw_status(
    screen: pygame.Surface,
    board: CBoard,
    bot_thinking: bool,
    note: str,
    player_color: Color,
    analyzing: bool = False,
):
    """Status bar under the board, spanning the eval bar + board width."""
    your_turn = not board.game_over and not bot_thinking and not note and board.turn == player_color
    bar = pygame.Surface((MOVELIST_W, STATUS_H), pygame.SRCALPHA)
    bar.fill(STATUS_TURN_BG if your_turn else STATUS_BG)
    screen.blit(bar, (0, BOARD_PX))

    if board.game_over:
        return  # game-over overlay covers this

    player_name = "White" if player_color == Color.WHITE else "Black"
    bot_name = "Black" if player_color == Color.WHITE else "White"
    font = pygame.font.SysFont(None, 28)
    if note:
        msg, color = note, (255, 140, 140)
    elif analyzing:
        msg, color = "Analyzing...", (120, 205, 205)
    elif bot_thinking:
        msg, color = "Bot is thinking...", (200, 200, 100)
    elif your_turn:
        msg, color = f"Your turn  ({player_name})", (245, 245, 245)
    else:
        msg, color = f"Bot's turn  ({bot_name})", (160, 160, 255)

    text = font.render(msg, True, color)
    screen.blit(text, (10, BOARD_PX + 8))


def draw_captured_tray(screen: pygame.Surface, x: int, y: int, width: int, board: CBoard) -> int:
    """Each side's captured pieces and the net material advantage (no heading;
    the collapsible header supplies the title)."""
    material = {Color.WHITE: 0, Color.BLACK: 0}
    captured = {Color.WHITE: [], Color.BLACK: []}  # pieces each color has taken
    for color in Color:
        for piece in PieceType:
            count = bin(board.get_specific_pieces(color, piece)).count("1")
            material[color] += _PIECE_VALUE[piece] * count
            missing = _START_COUNTS[piece] - count
            captured[color.opponent()].extend([piece] * max(0, missing))

    font = pygame.font.SysFont(None, 20)
    for color, label in ((Color.WHITE, "White"), (Color.BLACK, "Black")):
        screen.blit(font.render(label, True, sidebar.MUTED_COL), (x, y + 2))
        px = x + 56
        for piece in sorted(captured[color], key=lambda p: -_PIECE_VALUE[p]):
            screen.blit(SMALL_IMAGES[(color.opponent(), piece)], (px, y))
            px += 18
        y += 26

    adv = material[Color.WHITE] - material[Color.BLACK]
    if adv != 0:
        leader = "White" if adv > 0 else "Black"
        screen.blit(font.render(f"{leader} +{abs(adv)}", True, sidebar.TEXT_COL), (x, y))
    y += 24
    return y + 6


def main(args):
    pygame.init()
    screen = pygame.display.set_mode(
        (WINDOW_W, WINDOW_H), pygame.SCALED | pygame.RESIZABLE | pygame.WINDOWMAXIMIZED
    )
    pygame.display.set_caption("ESCHESS")
    clock = pygame.time.Clock()

    board = CBoard()
    load_assets()

    # Availability of the optional backends, for greying out menu controls.
    avail = {
        "cpp": engine_backend.cpp_available(args.cpp_command),
        "rust": engine_backend.rust_available(args.rust_command),
        "value": engine_backend.has_weights("value"),
        "policy": engine_backend.has_weights("policy"),
        "value_rl": engine_backend.has_rl_weights("value"),
        "policy_rl": engine_backend.has_rl_weights("policy"),
    }

    # Live-editable settings
    applied = {
        "lang": args.lang,
        "search": args.search,
        "eval": args.eval,
        "weights": args.weights,
        "depth": args.depth,
    }  # current engine
    pending = dict(applied)  # menu settings

    def build_engine(settings):
        return make_engine(
            lang=settings["lang"],
            search=settings["search"],
            evaluator=settings["eval"],
            device=args.device,
            cpp_command=args.cpp_command,
            rust_command=args.rust_command,
            weights_source=settings["weights"],
        )

    engine = build_engine(applied)
    status_note = ""

    probe = eval_probe.StockfishProbe()
    probe.request(board.to_fen())

    toggles = {"eval_bar": True, "last_move": True}
    collapsed = {"captured": False, "moves": False}
    show_extras = False
    viz_mode = "pv"  # off | pv | top3 | density
    # Suppress the search overlays after stepping back through moves
    viz_stale = False
    player_color = PLAYER_COLOR
    bot_color = BOT_COLOR
    move_time_ms = 0  # per-move search budget; 0 = depth-limited only

    selected_sq: int | None = None
    legal_mask: int = 0
    promo_pending: tuple[int, int] | None = None
    promo_rects: list[tuple[pygame.Rect, PieceType]] = []
    move_log: list[tuple] = []
    cursor = 0
    last_move: tuple[int, int] | None = None
    move_scroll = 0  # rows scrolled up from the bottom of the list
    move_max_scroll = 0

    # Bot state: mutated from background thread via dict to avoid nonlocal rebinding.
    # 'apply' distinguishes a real move (played on the board) from a Re-evaluate
    # pass (telemetry only, move discarded).
    bot: dict = {"thinking": False, "move": None, "apply": True}
    menu_hotspots: list = []
    gear_rect = pygame.Rect(WINDOW_W - 34, 8, 26, 26)

    def _depth_cap() -> int:
        return 5 if pending["lang"] == "py" else 8

    def _check_game_over():
        if board.is_checkmate():
            board.game_over = True
            board.winner = board.turn.opponent()
        elif board.is_stalemate():
            board.game_over = True
            board.winner = None

    def _record_move(move):
        nonlocal last_move, cursor, move_scroll
        if cursor < len(move_log):
            del move_log[cursor:]
        move_log.append(move)
        cursor = len(move_log)
        last_move = (move[0], move[1])
        move_scroll = 0
        probe.request(board.to_fen())

    def _start_engine(apply: bool):
        """Run the engine on the current position in a daemon thread. apply=True
        plays the result (a real bot move); apply=False just refreshes the
        visualization telemetry (Re-evaluate)."""
        nonlocal viz_stale
        if bot["thinking"] or board.game_over:
            return
        bot["thinking"] = True
        bot["apply"] = apply
        viz_stale = False  # a fresh search is starting; overlays are live again
        board_copy = copy.deepcopy(board)
        depth = applied["depth"]
        time_limit = move_time_ms or None

        def _run():
            bot["move"] = engine.get_best_move(board_copy, depth, time_limit)
            bot["thinking"] = False

        # Daemon thread: auto terminates as all non-daemon threads finish
        threading.Thread(target=_run, daemon=True).start()

    def _trigger_bot():
        if board.turn != bot_color:
            return
        _start_engine(apply=True)

    def _reevaluate():
        """Recompute the engine's view of the current position for the overlays
        (e.g. after stepping back through moves)."""
        _start_engine(apply=False)

    def _force_move():
        """Cut off the engine's current think; iterative deepening means it falls
        back to the best move from the last completed depth."""
        if bot["thinking"] and hasattr(engine, "stop"):
            engine.stop()

    def _refresh_last_move():
        nonlocal last_move
        last_move = (move_log[cursor - 1][0], move_log[cursor - 1][1]) if cursor > 0 else None

    def _undo():
        """Step back to the previous position where it's the player's turn."""
        nonlocal cursor, move_scroll, viz_stale
        if bot["thinking"] or cursor == 0:
            return
        while cursor > 0:
            board.unmake_move()
            cursor -= 1
            if board.turn == player_color:
                break
        board.game_over = False
        board.winner = None
        _refresh_last_move()
        move_scroll = 0
        viz_stale = True  # arrows now describe a position we've left; hide them

    def _redo():
        """Replay the redo tail forward to the next player-to-move position."""
        nonlocal cursor, move_scroll, viz_stale
        if bot["thinking"] or cursor >= len(move_log):
            return
        while cursor < len(move_log):
            f, t, promo = move_log[cursor]
            board.make_move(f, t, promo)
            cursor += 1
            if board.turn == player_color:
                break
        _refresh_last_move()
        _check_game_over()
        move_scroll = 0
        viz_stale = True

    def _apply_settings():
        """Rebuild the engine from 'pending'; revert and warn on failure."""
        nonlocal engine, applied, status_note
        if pending == applied:
            return
        try:
            new_engine = build_engine(pending)
        except Exception as exc:  # missing weights/binary despite UI guards
            status_note = f"settings failed: {exc}"[:48]
            pending.update(applied)
            return
        if hasattr(engine, "close"):
            engine.close()
        engine = new_engine
        applied = dict(pending)
        status_note = ""
        _apply_multipv()  # re-apply the current visualization to the new engine

    def _analysis_ok() -> bool:
        """Top-3 / density need a tree search; the policy net has none."""
        return not (applied["lang"] == "py" and applied["search"] == "policy")

    def _apply_multipv():
        nonlocal viz_mode
        if viz_mode in ("top3", "density") and not _analysis_ok():
            viz_mode = "pv"
        # Run the full top-3 analysis whenever any tree-search overlay is on.
        want_full = viz_mode != "off" and _analysis_ok()
        engine.set_multipv(3 if want_full else 1)

    def _set_viz(mode):
        nonlocal viz_mode
        viz_mode = mode
        _apply_multipv()

    def _normalize_weights():
        """Keep the weights source on a source that actually has the active net's
        checkpoints, so selecting 'nn'/'policy' just works when only one exists."""
        kind = "policy" if pending["search"] == "policy" else "value"
        if pending["weights"] == "supervised" and not avail[kind] and avail[f"{kind}_rl"]:
            pending["weights"] = "rl"
        elif pending["weights"] == "rl" and not avail[f"{kind}_rl"] and avail[kind]:
            pending["weights"] = "supervised"

    def _set_pending(key, value):
        pending[key] = value
        if key == "lang":
            pending["depth"] = min(pending["depth"], _depth_cap())
        if key in ("search", "eval", "weights"):
            _normalize_weights()
        # Apply immediately when the engine is idle (player's turn); otherwise the
        # change is staged and applied once the bot finishes its current move.
        if not bot["thinking"]:
            _apply_settings()

    def _reset(new_player_color: Color | None = None):
        nonlocal board, player_color, bot_color, selected_sq, legal_mask, promo_pending
        nonlocal last_move, status_note, cursor, move_scroll, viz_stale
        global FLIPPED
        if bot["thinking"]:
            return
        if new_player_color is not None:
            player_color = new_player_color
            bot_color = new_player_color.opponent()
            FLIPPED = player_color == Color.BLACK  # show the human's side at the bottom
        board = CBoard()
        selected_sq, legal_mask, promo_pending, last_move = None, 0, None, None
        move_log.clear()
        cursor = 0
        move_scroll = 0
        viz_stale = False
        bot["move"] = None
        bot["apply"] = True
        status_note = ""
        if hasattr(engine, "new_game"):
            engine.new_game()  # clear killers/history between games
        probe.request(board.to_fen())
        if board.turn == bot_color:
            _trigger_bot()  # human plays Black: the bot (White) opens

    def _flip():
        """Rotate the board view without disturbing the game."""
        global FLIPPED
        FLIPPED = not FLIPPED

    _apply_multipv()  # match the engine's MultiPV to the initial visualization mode

    running = True
    while running:
        # Consume the background thread's result. A real bot move (apply) gets
        # played; a Re-evaluate pass only refreshed the overlays, so it's discarded.
        if not bot["thinking"] and bot["move"] is not None:
            move = bot["move"]
            bot["move"] = None
            if bot["apply"] and move is not None and not board.game_over:
                from_square, to_square, promotion = move
                board.make_move(from_square, to_square, promotion)
                _record_move((from_square, to_square, promotion))
                _check_game_over()

        if not bot["thinking"] and pending != applied:
            _apply_settings()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            elif event.type == pygame.MOUSEWHEEL:
                move_scroll = max(0, min(move_scroll + event.y, move_max_scroll))

            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_r and not bot["thinking"]:
                    _reset()

            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                # 1) Menu / gear / section interactions are always available.
                hit = next((hs for hs in menu_hotspots if hs.rect.collidepoint(event.pos)), None)
                if hit is not None:
                    kind = hit.action[0]
                    if kind == "gear":
                        show_extras = not show_extras
                    elif kind == "toggle_extra":
                        toggles[hit.action[1]] = not toggles[hit.action[1]]
                    elif kind == "collapse":
                        collapsed[hit.action[1]] = not collapsed[hit.action[1]]
                    elif kind == "undo":
                        _undo()
                    elif kind == "redo":
                        _redo()
                    elif kind == "viz":
                        _set_viz(hit.action[1])
                    elif kind == "set":
                        _set_pending(hit.action[1], hit.action[2])
                    elif kind == "depth":
                        _, lo, hi = hit.action
                        _set_pending(
                            "depth", sidebar.depth_from_click(hit.rect, event.pos[0], lo, hi)
                        )
                    elif kind == "movetime":
                        _, lo, hi = hit.action
                        val = sidebar.slider_value_from_click(hit.rect, event.pos[0], lo, hi)
                        move_time_ms = int(round(val / 500) * 500)  # snap to 0.5s steps
                    elif kind == "reeval":
                        _reevaluate()
                    elif kind == "force":
                        _force_move()
                    elif kind == "newgame":
                        _reset(Color.WHITE if hit.action[1] == "white" else Color.BLACK)
                    elif kind == "flip":
                        _flip()
                    continue
                # Click outside an open extras menu closes it.
                if show_extras and not gear_rect.collidepoint(event.pos):
                    show_extras = False
                    continue

                # 2) Board interactions (player's turn only).
                if bot["thinking"] or board.turn != player_color:
                    continue

                if promo_pending is not None:
                    for rect, pt in promo_rects:
                        if rect.collidepoint(event.pos):
                            board.make_move(promo_pending[0], promo_pending[1], promotion=pt)
                            _record_move((promo_pending[0], promo_pending[1], pt))
                            promo_pending = None
                            selected_sq = None
                            legal_mask = 0
                            _check_game_over()
                            _trigger_bot()
                    continue

                if board.game_over:
                    continue

                clicked_sq = screen_to_sq(*event.pos)
                if clicked_sq < 0:
                    continue

                if selected_sq is None:
                    info = board.get_piece_at(clicked_sq)
                    if info and info[0] == board.turn:
                        selected_sq = clicked_sq
                        legal_mask = board.get_legal_moves(clicked_sq)
                else:
                    if legal_mask & (1 << clicked_sq):
                        if board.needs_promotion(selected_sq, clicked_sq):
                            promo_pending = (selected_sq, clicked_sq)
                        else:
                            board.make_move(selected_sq, clicked_sq)
                            _record_move((selected_sq, clicked_sq, None))
                            selected_sq = None
                            legal_mask = 0
                            _check_game_over()
                            _trigger_bot()
                    else:
                        info = board.get_piece_at(clicked_sq)
                        if info and info[0] == board.turn:
                            selected_sq = clicked_sq
                            legal_mask = board.get_legal_moves(clicked_sq)
                        else:
                            selected_sq = None
                            legal_mask = 0

        # ── Draw ──────────────────────────────────────────────────────────────
        screen.fill(WINDOW_BG)

        if toggles["eval_bar"]:
            score = (
                probe.score
                if (probe.available and probe.score is not None)
                else engine.last_info.get("score")
            )
            eval_probe.draw_eval_bar(
                screen, pygame.Rect(0, 0, EVAL_BAR_W, BOARD_PX), score, flipped=FLIPPED
            )

        draw_board(screen, selected_sq, last_move if toggles["last_move"] else None)
        draw_pieces(screen, board)
        if not board.game_over and promo_pending is None:
            draw_move_dots(screen, board, legal_mask)
        # Overlays are hidden after stepping back (viz_stale) until Re-evaluate runs.
        if viz_mode != "off" and not viz_stale and not board.game_over and promo_pending is None:
            if viz_mode == "pv":
                draw_search_arrows(screen, engine.last_info.get("pv", []))
            elif viz_mode == "top3":
                draw_top3_arrows(
                    screen,
                    engine.last_info.get("multipv", []),
                    engine.last_info.get("stm_white", True),
                )
            elif viz_mode == "density":
                draw_density_cloud(screen, engine.last_info.get("effort", {}))

        if promo_pending is not None:
            promo_rects = draw_promotion_picker(screen, player_color)

        if board.game_over:
            draw_game_over(screen, board)

        draw_status(
            screen, board, bot["thinking"], status_note, player_color,
            analyzing=bot["thinking"] and not bot["apply"],
        )

        # ── Right menu ──────────────────────────────────────────────────────────
        pygame.draw.rect(screen, sidebar.PANEL_BG, (MENU_X, 0, MENU_W, WINDOW_H))
        menu_hotspots = []
        mx = MENU_X + sidebar.PAD
        mw = MENU_W - 2 * sidebar.PAD
        my = 12

        my, hs = sidebar.draw_engine_settings(
            screen, mx, my, mw, pending, avail, pending != applied
        )
        menu_hotspots.extend(hs)
        my = sidebar.draw_performance(screen, mx, my, mw, engine.last_info)

        my, hs = sidebar.draw_visualization(screen, mx, my, mw, viz_mode, _analysis_ok())
        menu_hotspots.extend(hs)

        my, hs = sidebar.draw_engine_control(
            screen, mx, my, mw, move_time_ms, bot["thinking"], can_reeval=viz_mode != "off"
        )
        menu_hotspots.extend(hs)

        my, hs = sidebar.draw_game_controls(
            screen, mx, my, mw, player_color == Color.WHITE, FLIPPED, bot["thinking"]
        )
        menu_hotspots.extend(hs)

        hs, my = sidebar.draw_collapsible_header(
            screen, mx, my, mw, "Captured", collapsed["captured"], "captured"
        )
        menu_hotspots.extend(hs)
        if not collapsed["captured"]:
            my = draw_captured_tray(screen, mx, my, mw, board)

        menu_hotspots.append(sidebar.draw_gear(screen, gear_rect, show_extras))
        if show_extras:
            menu_hotspots.extend(sidebar.draw_extras_menu(screen, gear_rect, toggles))

        # ── Move list (below the board) ─────────────────────────────────────────
        mlx = sidebar.PAD
        mlw = MOVELIST_W - 2 * sidebar.PAD
        hs, body_y = sidebar.draw_collapsible_header(
            screen, mlx, MOVELIST_Y + 6, mlw, "Moves", collapsed["moves"], "moves", nav=True
        )
        menu_hotspots.extend(hs)
        if not collapsed["moves"]:
            list_rect = pygame.Rect(mlx, body_y, mlw, WINDOW_H - body_y - sidebar.PAD)
            move_max_scroll = sidebar.draw_move_list(
                screen, list_rect, move_log, cursor, move_scroll
            )

        pygame.display.flip()
        clock.tick(FPS)

    probe.close()
    if hasattr(engine, "close"):
        engine.close()
    pygame.quit()
    sys.exit()


def parse_args():
    parser = argparse.ArgumentParser(description="Play chess against the eschess bot.")
    parser.add_argument(
        "--lang",
        choices=("py", "cpp", "rust"),
        default="py",
        help="bot implementation: in-process Python, or external C++/Rust UCI binary",
    )
    parser.add_argument(
        "--search",
        choices=("alphabeta", "policy"),
        default="alphabeta",
        help="Python move source: alpha-beta tree search or the policy network",
    )
    parser.add_argument(
        "--eval",
        choices=("simple", "medium", "complex", "nn"),
        default="medium",
        help="evaluation for alpha-beta search; 'nn' is the value network "
        "(ignored when --search policy or --lang cpp)",
    )
    parser.add_argument(
        "--weights",
        choices=("supervised", "rl"),
        default="supervised",
        help="network checkpoints for 'nn' eval / 'policy' search: "
        "supervised (nn/weights) or self-play RL (nn/weights/rl)",
    )
    parser.add_argument("--depth", type=int, default=BOT_DEPTH, help="bot search depth")
    parser.add_argument("--device", default="cpu", help="torch device for the networks")
    parser.add_argument("--cpp-command", default=None, help="override the C++ UCI binary path")
    parser.add_argument("--rust-command", default=None, help="override the Rust UCI binary path")
    return parser.parse_args()


if __name__ == "__main__":
    main(parse_args())
