"""
Date created: Jun 13
Author: Kane Weng

Main execution file for a chess game using pygame.
"""

import pygame
import sys
from board import CBoard, Color, PieceType

SQUARE_SIZE = 80
PIECE_SIZE  = int(SQUARE_SIZE * 0.8)
WIDTH = HEIGHT = SQUARE_SIZE * 8
FPS = 60

LIGHT_SQ   = pygame.Color(240, 217, 181)
DARK_SQ    = pygame.Color(181, 136,  99)
HIGHLIGHT  = (255, 255,   0, 140)  # yellow, semi-transparent
DOT_COLOR  = (  0,   0,   0, 150)  # black dot, semi-transparent
CAPTURE_RG = (180,   0,   0, 120)  # red ring on capturable squares

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
            filename = f"assets/{color_chars[color]}_{piece_chars[piece]}_png_1024px.png"
            img = pygame.image.load(filename).convert_alpha()
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


def main():
    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("ESCHESS")
    clock = pygame.time.Clock()

    board = CBoard()
    load_assets()

    selected_sq: int | None = None
    legal_mask: int = 0
    # Promotion state: pending move waiting for piece choice
    promo_pending: tuple[int, int] | None = None   # (from_sq, to_sq)
    promo_rects: list[tuple[pygame.Rect, PieceType]] = []

    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_r:
                    board = CBoard()
                    selected_sq = None
                    legal_mask  = 0
                    promo_pending = None

            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if promo_pending is not None:
                    for rect, pt in promo_rects:
                        if rect.collidepoint(event.pos):
                            board.make_move(promo_pending[0], promo_pending[1], promotion=pt)
                            promo_pending = None
                            selected_sq   = None
                            legal_mask    = 0
                            if board.is_checkmate():
                                board.game_over = True
                                board.winner = board.turn.opponent()
                            elif board.is_stalemate():
                                board.game_over = True
                                board.winner = None
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
                            if board.is_checkmate():
                                board.game_over = True
                                board.winner = board.turn.opponent()
                            elif board.is_stalemate():
                                board.game_over = True
                                board.winner = None
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
            promo_color = board.turn 
            promo_rects = draw_promotion_picker(screen, promo_color)

        if board.game_over:
            draw_game_over(screen, board)

        pygame.display.flip()
        clock.tick(FPS)

    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()
