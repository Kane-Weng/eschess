"""
Date created: Jun 13
Author: Kane Weng

Main execution file for a chess game using pygame.
"""

import argparse
import pygame
import sys
import threading
import copy
from pathlib import Path
from engine.board import CBoard, Color, PieceType
from engine_backend import make_engine

ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"

SQUARE_SIZE = 80
PIECE_SIZE  = int(SQUARE_SIZE * 0.8)
WIDTH       = SQUARE_SIZE * 8
HEIGHT      = SQUARE_SIZE * 8 + 36   # extra strip for status bar
FPS = 60

PLAYER_COLOR = Color.WHITE
BOT_COLOR    = Color.BLACK
BOT_DEPTH    = 3

LIGHT_SQ   = pygame.Color(240, 217, 181)
DARK_SQ    = pygame.Color(181, 136,  99)
HIGHLIGHT  = (255, 255,   0, 140)  # yellow, semi-transparent
DOT_COLOR  = (  0,   0,   0, 150)  # black dot, semi-transparent
CAPTURE_RG = (180,   0,   0, 120)  # red ring on capturable squares
STATUS_BG  = (30,  30,  30, 220)

IMAGES: dict[tuple[Color, PieceType], pygame.Surface] = {}

PROMO_PIECES = [PieceType.QUEEN, PieceType.ROOK, PieceType.BISHOP, PieceType.KNIGHT]


def load_assets():
    color_chars = {Color.WHITE: 'w', Color.BLACK: 'b'}
    piece_chars = {
        PieceType.PAWN: 'pawn', PieceType.KNIGHT: 'knight', PieceType.BISHOP: 'bishop',
        PieceType.ROOK: 'rook', PieceType.QUEEN: 'queen',   PieceType.KING: 'king',
    }
    for color in Color:
        for piece in PieceType:
            filename = ASSETS_DIR / f"{color_chars[color]}_{piece_chars[piece]}_png_1024px.png"
            img = pygame.image.load(str(filename)).convert_alpha()
            IMAGES[(color, piece)] = pygame.transform.smoothscale(img, (PIECE_SIZE, PIECE_SIZE))


def sq_to_screen(sq: int) -> tuple[int, int]:
    """Top-left pixel of the square."""
    file_idx = CBoard.get_file_idx(sq)
    rank_idx = CBoard.get_rank_idx(sq)
    return file_idx * SQUARE_SIZE, (7 - rank_idx) * SQUARE_SIZE


def screen_to_sq(x: int, y: int) -> int:
    file_idx = x // SQUARE_SIZE
    rank_idx = 7 - y // SQUARE_SIZE
    if not (0 <= file_idx <= 7 and 0 <= rank_idx <= 7):
        return -1
    return CBoard.get_square_idx(rank_idx, file_idx)


def draw_board(screen: pygame.Surface, selected_sq: int | None):
    for sq in range(64):
        file_idx = CBoard.get_file_idx(sq)
        rank_idx = CBoard.get_rank_idx(sq)
        color = LIGHT_SQ if (rank_idx + file_idx) % 2 == 0 else DARK_SQ
        x, y = sq_to_screen(sq)
        pygame.draw.rect(screen, color, (x, y, SQUARE_SIZE, SQUARE_SIZE))

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
            pygame.draw.circle(dot_surf, CAPTURE_RG,
                               (SQUARE_SIZE // 2, SQUARE_SIZE // 2),
                               SQUARE_SIZE // 2, 6)
        else:
            pygame.draw.circle(dot_surf, DOT_COLOR,
                               (SQUARE_SIZE // 2, SQUARE_SIZE // 2),
                               SQUARE_SIZE // 7)
        screen.blit(dot_surf, (x, y))


def draw_promotion_picker(screen: pygame.Surface, color: Color) -> list[tuple[pygame.Rect, PieceType]]:
    """Draw the promotion picker overlay and return clickable rects."""
    overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, 160))
    screen.blit(overlay, (0, 0))

    num = len(PROMO_PIECES)
    box_w = SQUARE_SIZE + 20
    box_h = SQUARE_SIZE + 20
    total_w = num * box_w + (num - 1) * 10
    start_x = (WIDTH - total_w) // 2
    y = (HEIGHT - box_h) // 2

    rects: list[tuple[pygame.Rect, PieceType]] = []
    font = pygame.font.SysFont(None, 22)
    labels = {PieceType.QUEEN: "Queen", PieceType.ROOK: "Rook",
              PieceType.BISHOP: "Bishop", PieceType.KNIGHT: "Knight"}

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
    screen.blit(overlay, (0, 0))

    font_big = pygame.font.SysFont(None, 72)
    font_sm  = pygame.font.SysFont(None, 36)

    if board.winner is None:
        msg = "Stalemate - Draw"
    elif board.winner == Color.WHITE:
        msg = "White Wins!"
    else:
        msg = "Black Wins!"

    text = font_big.render(msg, True, (255, 255, 255))
    sub  = font_sm.render("Press R to restart", True, (200, 200, 200))
    screen.blit(text, text.get_rect(center=(WIDTH // 2, HEIGHT // 2 - 24)))
    screen.blit(sub,  sub.get_rect(center=(WIDTH // 2, HEIGHT // 2 + 36)))


def draw_status(screen: pygame.Surface, board: CBoard, bot_thinking: bool):
    """Status bar rendered below the board."""
    bar = pygame.Surface((WIDTH, 36), pygame.SRCALPHA)
    bar.fill(STATUS_BG)
    screen.blit(bar, (0, SQUARE_SIZE * 8))

    if board.game_over:
        return  # game-over overlay covers this

    font = pygame.font.SysFont(None, 28)
    if bot_thinking:
        msg = "Bot is thinking..."
        color = (200, 200, 100)
    elif board.turn == PLAYER_COLOR:
        msg = "Your turn  (White)"
        color = (220, 220, 220)
    else:
        msg = "Bot's turn  (Black)"
        color = (160, 160, 255)

    text = font.render(msg, True, color)
    screen.blit(text, (10, SQUARE_SIZE * 8 + 8))


def main(args):
    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("ESCHESS")
    clock = pygame.time.Clock()

    board = CBoard()
    load_assets()
    # Bot brain chosen by the command line args (Python or C++, alpha-beta or
    # policy net, and the evaluation level). See engine_backend.py.
    search = make_engine(
        lang=args.lang, search=args.search, evaluator=args.eval,
        device=args.device, cpp_command=args.cpp_command,
        rust_command=args.rust_command,
    )
    bot_depth = args.depth

    selected_sq: int | None = None
    legal_mask: int = 0
    promo_pending: tuple[int, int] | None = None
    promo_rects: list[tuple[pygame.Rect, PieceType]] = []

    # Bot state: mutated from background thread via dict to avoid nonlocal rebinding
    bot: dict = {"thinking": False, "move": None}

    def _check_game_over():
        if board.is_checkmate():
            board.game_over = True
            board.winner = board.turn.opponent()
        elif board.is_stalemate():
            board.game_over = True
            board.winner = None

    def _trigger_bot():
        if board.game_over or board.turn != BOT_COLOR:
            return
        bot["thinking"] = True
        board_copy = copy.deepcopy(board)

        def _run():
            bot["move"] = search.get_best_move(board_copy, bot_depth)
            bot["thinking"] = False

        # Daemon thread: auto terminates as all non-daemon threads finish
        threading.Thread(target=_run, daemon=True).start()

    running = True
    while running:
        # Apply bot move when the background thread has finished
        if not bot["thinking"] and bot["move"] is not None and not board.game_over:
            from_square, to_square, promotion = bot["move"]
            bot["move"] = None
            board.make_move(from_square, to_square, promotion)
            _check_game_over()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_r and not bot["thinking"]:
                    board = CBoard()
                    selected_sq   = None
                    legal_mask    = 0
                    promo_pending = None
                    bot["move"]   = None

            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                # Block all clicks while the bot is computing or it's not the player's turn
                if bot["thinking"] or board.turn != PLAYER_COLOR:
                    continue

                if promo_pending is not None:
                    for rect, pt in promo_rects:
                        if rect.collidepoint(event.pos):
                            board.make_move(promo_pending[0], promo_pending[1], promotion=pt)
                            promo_pending = None
                            selected_sq   = None
                            legal_mask    = 0
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
                        legal_mask  = board.get_legal_moves(clicked_sq)
                else:
                    if legal_mask & (1 << clicked_sq):
                        if board.needs_promotion(selected_sq, clicked_sq):
                            promo_pending = (selected_sq, clicked_sq)
                        else:
                            board.make_move(selected_sq, clicked_sq)
                            selected_sq = None
                            legal_mask  = 0
                            _check_game_over()
                            _trigger_bot()
                    else:
                        info = board.get_piece_at(clicked_sq)
                        if info and info[0] == board.turn:
                            selected_sq = clicked_sq
                            legal_mask  = board.get_legal_moves(clicked_sq)
                        else:
                            selected_sq = None
                            legal_mask  = 0

        # Draw
        draw_board(screen, selected_sq)
        draw_pieces(screen, board)
        if not board.game_over and promo_pending is None:
            draw_move_dots(screen, board, legal_mask)

        if promo_pending is not None:
            promo_rects = draw_promotion_picker(screen, PLAYER_COLOR)

        if board.game_over:
            draw_game_over(screen, board)

        draw_status(screen, board, bot["thinking"])

        pygame.display.flip()
        clock.tick(FPS)

    pygame.quit()
    sys.exit()


def parse_args():
    parser = argparse.ArgumentParser(description="Play chess against the eschess bot.")
    parser.add_argument("--lang", choices=("py", "cpp", "rust"), default="py",
                        help="bot implementation: in-process Python, or external C++/Rust UCI binary")
    parser.add_argument("--search", choices=("alphabeta", "policy"), default="alphabeta",
                        help="Python move source: alpha-beta tree search or the policy network")
    parser.add_argument("--eval", choices=("simple", "medium", "complex", "nn"), default="medium",
                        help="evaluation for alpha-beta search; 'nn' is the value network "
                             "(ignored when --search policy or --lang cpp)")
    parser.add_argument("--depth", type=int, default=BOT_DEPTH, help="bot search depth")
    parser.add_argument("--device", default="cpu", help="torch device for the networks")
    parser.add_argument("--cpp-command", default=None, help="override the C++ UCI binary path")
    parser.add_argument("--rust-command", default=None, help="override the Rust UCI binary path")
    return parser.parse_args()


if __name__ == "__main__":
    main(parse_args())
