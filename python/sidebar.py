"""
Date created: Jun 15
Author: Kane Weng

Right-hand control panel for the pygame GUI. Plain-pygame widgets
with no extra deps: a segmented toggle group, a depth slider, telemetry/move
panels, and the gear-toggle extras checklist.
"""

from collections import namedtuple

import pygame

from engine.board import square_name

# A clickable region and the action it triggers (a tuple inspected by main.py).
Hotspot = namedtuple("Hotspot", "rect action")

# -- Palette ------------------------------------------------------------------
PANEL_BG     = (24,  24,  28)
TITLE_COL    = (235, 235, 240)
TEXT_COL     = (205, 205, 210)
MUTED_COL    = (140, 140, 148)
BTN_BG       = (52,  52,  60)
BTN_SEL_BG   = (66, 120, 200)
BTN_DIS_BG   = (38,  38,  44)
BTN_DIS_TXT  = (92,  92,  100)
TRACK_BG     = (52,  52,  60)
TRACK_FILL   = (66, 120, 200)
PAD          = 14
ROW_H        = 30

_FONTS: dict[tuple[str, int, bool], pygame.font.Font] = {}


def _font(size: int, bold: bool = False) -> pygame.font.Font:
    key = ("sys", size, bold)
    if key not in _FONTS:
        f = pygame.font.SysFont(None, size)
        f.set_bold(bold)
        _FONTS[key] = f
    return _FONTS[key]


def _title(screen, text, x, y) -> int:
    screen.blit(_font(24, True).render(text, True, TITLE_COL), (x, y))
    return y + 30


def _label(screen, text, x, y) -> int:
    screen.blit(_font(20).render(text, True, MUTED_COL), (x, y))
    return y + 22


def _segment(screen, x, y, width, options, current, action_for,
             enabled, hotspots) -> int:
    """A row of equal-width buttons; 'enabled' maps option->bool."""
    n = len(options)
    gap = 6
    bw = (width - gap * (n - 1)) // n
    font = _font(18)
    for i, opt in enumerate(options):
        rect = pygame.Rect(x + i * (bw + gap), y, bw, ROW_H)
        on = enabled.get(opt, True)
        selected = opt == current
        bg = BTN_SEL_BG if (selected and on) else (BTN_BG if on else BTN_DIS_BG)
        pygame.draw.rect(screen, bg, rect, border_radius=5)
        if selected and on:
            pygame.draw.rect(screen, (210, 225, 255), rect, 2, border_radius=5)
        txt_col = TEXT_COL if on else BTN_DIS_TXT
        label = font.render(opt, True, txt_col)
        screen.blit(label, label.get_rect(center=rect.center))
        if on:
            hotspots.append(Hotspot(rect, action_for(opt)))
    return y + ROW_H + 10


def _slider(screen, x, y, width, value, lo, hi, hotspots, enabled=True) -> int:
    """Depth slider; the whole track is one hotspot, value derived from click x.
    Disabled (e.g. policy mode, where depth is meaningless) renders greyed."""
    label = f"Depth: {value}   (max {hi})" if enabled else "Depth (n/a in policy mode)"
    screen.blit(_font(20).render(label, True, TEXT_COL if enabled else BTN_DIS_TXT), (x, y))
    y += 24
    track = pygame.Rect(x, y + 6, width, 8)
    pygame.draw.rect(screen, TRACK_BG if enabled else BTN_DIS_BG, track, border_radius=4)
    if enabled:
        frac = (value - lo) / (hi - lo) if hi > lo else 0
        pygame.draw.rect(screen, TRACK_FILL,
                         (track.x, track.y, int(track.width * frac), track.height),
                         border_radius=4)
        handle_x = track.x + int(track.width * frac)
        pygame.draw.circle(screen, (225, 235, 255), (handle_x, track.y + 4), 9)
        hotspots.append(Hotspot(pygame.Rect(x, y, width, 26), ("depth", lo, hi)))
    return y + 30


def depth_from_click(rect, mouse_x, lo, hi) -> int:
    """Map a click x within a slider track rect to an integer depth in [lo, hi]."""
    frac = (mouse_x - rect.x) / rect.width if rect.width else 0
    frac = max(0.0, min(1.0, frac))
    return round(lo + frac * (hi - lo))


def draw_engine_settings(screen, x, y, width, pending, avail, dirty) -> int:
    """Engine settings section. Returns the y below it; appends control hotspots."""
    hotspots: list[Hotspot] = []
    title = "Engine settings" + ("  *pending*" if dirty else "")
    y = _title(screen, title, x, y)

    is_py = pending["lang"] == "py"
    is_ab = pending["search"] == "alphabeta"

    y = _label(screen, "Language", x, y)
    y = _segment(screen, x, y, width, ["py", "cpp", "rust"], pending["lang"],
                 lambda o: ("set", "lang", o),
                 {"py": True, "cpp": avail["cpp"], "rust": avail["rust"]}, hotspots)

    y = _label(screen, "Move source" if is_py else "Move source (Python only)", x, y)
    y = _segment(screen, x, y, width, ["alphabeta", "policy"], pending["search"],
                 lambda o: ("set", "search", o),
                 {"alphabeta": is_py,
                  "policy": is_py and (avail["policy"] or avail["policy_rl"])}, hotspots)

    # C++/Rust share the simple/medium/complex tiers; only alpha-beta Python has 'nn'.
    eval_on = (is_py and is_ab) or not is_py
    nn_on = is_py and is_ab and (avail["value"] or avail["value_rl"])
    y = _label(screen, "Evaluation" if eval_on else "Evaluation (alpha-beta only)", x, y)
    y = _segment(screen, x, y, width, ["simple", "medium", "complex", "nn"],
                 pending["eval"], lambda o: ("set", "eval", o),
                 {"simple": eval_on, "medium": eval_on, "complex": eval_on,
                  "nn": nn_on}, hotspots)

    kind = "policy" if pending["search"] == "policy" else "value"
    net_active = is_py and ((is_ab and pending["eval"] == "nn") or pending["search"] == "policy")
    sup_on = net_active and avail[kind]
    rl_on  = net_active and avail[f"{kind}_rl"]
    y = _label(screen, "Weights" if net_active else "Weights (nn eval / policy only)", x, y)
    y = _segment(screen, x, y, width, ["supervised", "rl"], pending["weights"],
                 lambda o: ("set", "weights", o),
                 {"supervised": sup_on, "rl": rl_on}, hotspots)

    hi = 5 if is_py else 8
    depth_on = not (is_py and pending["search"] == "policy")
    y = _slider(screen, x, y, width, min(pending["depth"], hi), 2, hi, hotspots, depth_on)
    return y + 6, hotspots


def draw_visualization(screen, x, y, width, mode, analysis_ok) -> tuple[int, list]:
    """Search-visualization selector: Off / PV / Top 3 / Density (mutually
    exclusive). Top-3 and Density need a tree search, so they grey out when
    'analysis_ok' is false (e.g. policy mode)."""
    hotspots: list[Hotspot] = []
    y = _title(screen, "Visualization", x, y)
    opts = [("off", "Off"), ("pv", "PV"), ("top3", "Top 3"), ("density", "Density")]
    enabled = {"off": True, "pv": True, "top3": analysis_ok, "density": analysis_ok}
    n = len(opts)
    gap = 6
    bw = (width - gap * (n - 1)) // n
    font = _font(18)
    for i, (val, label) in enumerate(opts):
        rect = pygame.Rect(x + i * (bw + gap), y, bw, ROW_H)
        on = enabled[val]
        selected = val == mode
        bg = BTN_SEL_BG if (selected and on) else (BTN_BG if on else BTN_DIS_BG)
        pygame.draw.rect(screen, bg, rect, border_radius=5)
        if selected and on:
            pygame.draw.rect(screen, (210, 225, 255), rect, 2, border_radius=5)
        lab = font.render(label, True, TEXT_COL if on else BTN_DIS_TXT)
        screen.blit(lab, lab.get_rect(center=rect.center))
        if on:
            hotspots.append(Hotspot(rect, ("viz", val)))
    return y + ROW_H + 10, hotspots


def draw_performance(screen, x, y, width, last_info) -> int:
    """Engine performance panel: nodes / NPS / depth / think time."""
    y = _title(screen, "Engine performance", x, y)
    font = _font(20)
    lines = [
        f"Nodes:  {last_info.get('nodes', 0):,}",
        f"NPS:    {last_info.get('nps', 0):,}",
        f"Depth reached:  {last_info.get('depth', 0)}",
        f"Think time:  {last_info.get('time_s', 0.0):.2f}s",
    ]
    for line in lines:
        screen.blit(font.render(line, True, TEXT_COL), (x, y))
        y += 24
    return y + 6


def draw_collapsible_header(screen, x, y, width, title, collapsed, key,
                            nav=False) -> tuple[list, int]:
    """A section heading with a ▶/▼ collapse toggle and optional ◀ ▶ nav arrows."""
    hotspots: list[Hotspot] = []
    # Nav buttons come first so they win hit-testing over the full-width row.
    if nav:
        bw = 26
        right = pygame.Rect(x + width - bw, y, bw, 24)
        left = pygame.Rect(x + width - 2 * bw - 6, y, bw, 24)
        for rect, facing, action in ((left, "left", ("undo",)),
                                     (right, "right", ("redo",))):
            pygame.draw.rect(screen, BTN_BG, rect, border_radius=4)
            mx, my = rect.center
            arrow = ([(mx + 4, my - 6), (mx - 5, my), (mx + 4, my + 6)] if facing == "left"
                     else [(mx - 4, my - 6), (mx + 5, my), (mx - 4, my + 6)])
            pygame.draw.polygon(screen, TEXT_COL, arrow)
            hotspots.append(Hotspot(rect, action))

    row = pygame.Rect(x, y, width, 28)
    # collapse triangle: right-pointing when collapsed, down-pointing when open
    cx, cy = x + 7, y + 12
    if collapsed:
        pts = [(cx - 4, cy - 6), (cx + 5, cy), (cx - 4, cy + 6)]
    else:
        pts = [(cx - 6, cy - 4), (cx + 6, cy - 4), (cx, cy + 5)]
    pygame.draw.polygon(screen, TITLE_COL, pts)
    screen.blit(_font(24, True).render(title, True, TITLE_COL), (x + 20, y))
    hotspots.append(Hotspot(row, ("collapse", key)))
    return hotspots, y + 30


def draw_move_list(screen, rect, move_log, cursor, scroll_from_bottom) -> int:
    """Scrollable UCI move list (terminal-style). 'cursor' = moves applied on
    board; moves beyond it (redo tail) render greyed. Returns max scroll."""
    pygame.draw.rect(screen, (16, 16, 20), rect, border_radius=4)
    font = _font(26)
    line_h = 30
    rows = max(1, (rect.height - 8) // line_h)

    pairs = []  # (move_number, white_move, black_move, white_idx, black_idx)
    for i in range(0, len(move_log), 2):
        w, b = move_log[i], (move_log[i + 1] if i + 1 < len(move_log) else None)
        pairs.append((i // 2 + 1, w, b, i, i + 1))

    max_scroll = max(0, len(pairs) - rows)
    scroll = max(0, min(scroll_from_bottom, max_scroll))
    start = max(0, len(pairs) - rows - scroll)
    visible = pairs[start:start + rows]

    cy = rect.y + 6
    for num, w, b, wi, bi in visible:
        uci_w = square_name(w[0]) + square_name(w[1])
        uci_b = (square_name(b[0]) + square_name(b[1])) if b else ""
        col_w = TEXT_COL if wi < cursor else MUTED_COL
        col_b = TEXT_COL if bi < cursor else MUTED_COL
        screen.blit(font.render(f"{num:>3}.", True, MUTED_COL), (rect.x + 10, cy))
        screen.blit(font.render(uci_w, True, col_w), (rect.x + 70, cy))
        if uci_b:
            screen.blit(font.render(uci_b, True, col_b), (rect.x + 180, cy))
        cy += line_h
    return max_scroll


def draw_extras_menu(screen, anchor_rect, toggles) -> list[Hotspot]:
    """Dropdown checklist under the gear; returns its hotspots (incl. a backdrop)."""
    items = [
        ("eval_bar",  "Eval bar"),
        ("last_move", "Last-move highlight"),
    ]
    hotspots: list[Hotspot] = []
    w, row = 220, 30
    x = anchor_rect.right - w
    y = anchor_rect.bottom + 4
    panel = pygame.Rect(x, y, w, row * len(items) + 8)
    pygame.draw.rect(screen, (40, 40, 48), panel, border_radius=6)
    pygame.draw.rect(screen, (90, 90, 100), panel, 1, border_radius=6)

    font = _font(18)
    cy = y + 4
    for key, label in items:
        rect = pygame.Rect(x + 4, cy, w - 8, row)
        box = pygame.Rect(rect.x + 4, rect.y + 6, 18, 18)
        pygame.draw.rect(screen, (20, 20, 24), box, border_radius=3)
        if toggles.get(key, True):
            pygame.draw.rect(screen, (90, 200, 120), box.inflate(-6, -6), border_radius=2)
        screen.blit(font.render(label, True, TEXT_COL), (box.right + 8, rect.y + 7))
        hotspots.append(Hotspot(rect, ("toggle_extra", key)))
        cy += row
    return hotspots


def draw_gear(screen, rect, open_) -> Hotspot:
    """Gear button at the top-right; returns its hotspot."""
    bg = BTN_SEL_BG if open_ else BTN_BG
    pygame.draw.rect(screen, bg, rect, border_radius=6)
    cx, cy = rect.center
    pygame.draw.circle(screen, (225, 230, 240), (cx, cy), 9, 2)
    pygame.draw.circle(screen, (225, 230, 240), (cx, cy), 3)
    for k in range(8):
        import math
        a = k * math.pi / 4
        x1 = cx + int(9 * math.cos(a))
        y1 = cy + int(9 * math.sin(a))
        x2 = cx + int(13 * math.cos(a))
        y2 = cy + int(13 * math.sin(a))
        pygame.draw.line(screen, (225, 230, 240), (x1, y1), (x2, y2), 2)
    return Hotspot(rect, ("gear",))
