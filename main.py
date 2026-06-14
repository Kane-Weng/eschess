"""
Date created: Jun 13
Author: Kane Weng

Main execution file for a chess game using pygame.
"""

import pygame
import sys
from board import CBoard, Color, PieceType

SQUARE_SIZE = 80
PIECE_SIZE  = SQUARE_SIZE * 0.8
WIDTH = HEIGHT = SQUARE_SIZE * 8
FPS = 60
IMAGES = {}     # Global dictionary to cache piece images

def load_assets():
    """Loads image from ./assets/"""
    color_chars = {Color.WHITE: 'w', Color.BLACK: 'b'}
    piece_chars = {
        PieceType.PAWN: 'pawn', PieceType.KNIGHT: 'knight', PieceType.BISHOP: 'bishop',
        PieceType.ROOK: 'rook', PieceType.QUEEN: 'queen', PieceType.KING: 'king'
    }

    for color in Color:
        for piece in PieceType:
            filename = f"assets/{color_chars[color]}_{piece_chars[piece]}_png_1024px.png"
            img = pygame.image.load(filename)
            IMAGES[(color, piece)] = pygame.transform.scale(img, (PIECE_SIZE, PIECE_SIZE))

def draw_board(screen):
    """Draws the 8x8 checkered grid"""
    colors = [pygame.Color("white"), pygame.Color("gray")]

    for square_index in range(64):
        file_idx = CBoard.get_file_index(square_index)
        rank_idx = CBoard.get_rank_index(square_index)
        color_idx = (rank_idx + file_idx) % 2   # even/odd parity

        # Pygame sets Y=0 at the top; LERF sets rank 0 at the bottom
        x = file_idx * SQUARE_SIZE
        y = (7-rank_idx) * SQUARE_SIZE

        pygame.draw.rect(screen, colors[color_idx], pygame.Rect(x, y, SQUARE_SIZE, SQUARE_SIZE))

def draw_pieces(screen, board: CBoard):
    """Draws pieces on the active squares."""
    offset = (SQUARE_SIZE - PIECE_SIZE) // 2

    for color in Color:
        for piece in PieceType: 
            mask = CBoard.get_specific_pieces(board, color, piece)
            for square_index in CBoard.mask_to_squares(mask):
                file_idx = CBoard.get_file_index(square_index)
                rank_idx = CBoard.get_rank_index(square_index)
                x = file_idx * SQUARE_SIZE + offset
                y = (7 - rank_idx) * SQUARE_SIZE + offset
                screen.blit(IMAGES[(color, piece)], (x, y))

def main():
    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("ESCHESS")
    clock = pygame.time.Clock()

    board = CBoard()
    load_assets()

    running = True
    while running:
        # Handle Events like clicks and quitting
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

        # Draw Graphics
        draw_board(screen)
        draw_pieces(screen, board)

        # Update Display
        pygame.display.flip()
        clock.tick(FPS)

    pygame.quit()
    sys.exit()

if __name__ == "__main__":
    main()