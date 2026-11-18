"""Generate a 1024x1024 world-news poster PNG for Tuesday 17 November 2026."""

import math
import os
import struct
import zlib

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
WIDTH = 1024
HEIGHT = 1024

# Newsprint palette: warm paper, near-black ink, red & deep-blue accents
PAPER_BG = (246, 241, 231)
CARD_BG = (251, 248, 241)
ICON_BG = (238, 232, 220)
INK = (22, 22, 24)
MUTED_INK = (55, 52, 48)
RULE_COLOR = (196, 188, 174)
RED_ACCENT = (190, 34, 34)
BLUE_ACCENT = (22, 58, 114)
GOLD_ACCENT = (212, 162, 48)
WHITE = (255, 255, 255)

Color = tuple[int, int, int]
Point = tuple[float, float]


class Canvas:
    """1024x1024 RGB framebuffer with deterministic 2D drawing primitives."""

    def __init__(self, width: int, height: int, bg: Color) -> None:
        self.width = width
        self.height = height
        self.buf = bytearray(bytes(bg) * (width * height))

    def set_pixel(self, x: int, y: int, color: Color) -> None:
        if 0 <= x < self.width and 0 <= y < self.height:
            idx = (y * self.width + x) * 3
            self.buf[idx] = color[0]
            self.buf[idx + 1] = color[1]
            self.buf[idx + 2] = color[2]

    def fill_rect(self, x: int, y: int, w: int, h: int, color: Color) -> None:
        if w <= 0 or h <= 0:
            return
        x0 = max(0, x)
        y0 = max(0, y)
        x1 = min(self.width, x + w)
        y1 = min(self.height, y + h)
        if x0 >= x1 or y0 >= y1:
            return
        row_bytes = bytes(color) * (x1 - x0)
        stride = self.width * 3
        for row in range(y0, y1):
            start = row * stride + x0 * 3
            self.buf[start : start + len(row_bytes)] = row_bytes

    def stroke_rect(
        self, x: int, y: int, w: int, h: int, color: Color, thickness: int = 1
    ) -> None:
        if w <= 0 or h <= 0 or thickness <= 0:
            return
        self.fill_rect(x, y, w, thickness, color)
        self.fill_rect(x, y + h - thickness, w, thickness, color)
        self.fill_rect(x, y, thickness, h, color)
        self.fill_rect(x + w - thickness, y, thickness, h, color)

    def fill_circle(self, cx: int, cy: int, radius: int, color: Color) -> None:
        if radius <= 0:
            self.set_pixel(cx, cy, color)
            return
        r2 = radius * radius
        for dy in range(-radius, radius + 1):
            y = cy + dy
            if y < 0 or y >= self.height:
                continue
            dx_max = int(math.isqrt(r2 - dy * dy))
            x0 = max(0, cx - dx_max)
            x1 = min(self.width, cx + dx_max + 1)
            if x0 < x1:
                row_bytes = bytes(color) * (x1 - x0)
                start = (y * self.width + x0) * 3
                self.buf[start : start + len(row_bytes)] = row_bytes

    def draw_line(
        self, x0: int, y0: int, x1: int, y1: int, color: Color, thickness: int = 1
    ) -> None:
        """Draw a thick line by stamping filled squares along a Bresenham path."""
        dx = abs(x1 - x0)
        dy = abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx - dy
        half = thickness // 2

        while True:
            if thickness <= 1:
                self.set_pixel(x0, y0, color)
            else:
                self.fill_rect(x0 - half, y0 - half, thickness, thickness, color)
            if x0 == x1 and y0 == y1:
                break
            e2 = 2 * err
            if e2 > -dy:
                err -= dy
                x0 += sx
            if e2 < dx:
                err += dx
                y0 += sy

    def fill_polygon(self, points: list[Point], color: Color) -> None:
        """Scanline-fill a closed polygon defined by (x, y) vertices."""
        n = len(points)
        if n < 3:
            return
        min_y = max(0, int(math.floor(min(p[1] for p in points))))
        max_y = min(self.height - 1, int(math.ceil(max(p[1] for p in points))))
        stride = self.width * 3

        for y in range(min_y, max_y + 1):
            scan_y = y + 0.5
            intersections: list[float] = []
            for i in range(n):
                x1, y1 = points[i]
                x2, y2 = points[(i + 1) % n]
                if (y1 <= scan_y < y2) or (y2 <= scan_y < y1):
                    x_hit = x1 + (scan_y - y1) * (x2 - x1) / (y2 - y1)
                    intersections.append(x_hit)
            intersections.sort()
            for i in range(0, len(intersections) - 1, 2):
                xa = max(0, int(math.ceil(intersections[i] - 0.5)))
                xb = min(self.width - 1, int(math.floor(intersections[i + 1] - 0.5)))
                if xa <= xb:
                    row_bytes = bytes(color) * (xb - xa + 1)
                    start = y * stride + xa * 3
                    self.buf[start : start + len(row_bytes)] = row_bytes

    def to_png_bytes(self) -> bytes:
        """Encode the canvas buffer as a standard 8-bit RGB PNG."""
        ihdr_data = struct.pack(">IIBBBBB", self.width, self.height, 8, 2, 0, 0, 0)
        stride = self.width * 3
        raw = bytearray(self.height * (stride + 1))
        for y in range(self.height):
            dst = y * (stride + 1)
            raw[dst] = 0
            src = y * stride
            raw[dst + 1 : dst + 1 + stride] = self.buf[src : src + stride]
        compressed = zlib.compress(bytes(raw), 6)
        return b"".join(
            [
                PNG_SIGNATURE,
                _make_chunk(b"IHDR", ihdr_data),
                _make_chunk(b"IDAT", compressed),
                _make_chunk(b"IEND", b""),
            ]
        )


def _make_chunk(chunk_type: bytes, data: bytes) -> bytes:
    """Build a PNG chunk with length, type, payload, and CRC32."""
    crc = zlib.crc32(chunk_type + data) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + chunk_type + data + struct.pack(">I", crc)


# Stroke-vector font on a 7x11 grid: glyph -> (advance_width, list_of_polylines)
Glyph = tuple[int, list[list[tuple[int, int]]]]

FONT_GLYPHS: dict[str, Glyph] = {
    "A": (7, [[(0, 11), (3, 0), (4, 0), (7, 11)], [(1, 7), (6, 7)]]),
    "B": (
        7,
        [
            [(0, 11), (0, 0), (5, 0), (6, 1), (6, 4), (5, 5), (0, 5)],
            [(5, 5), (7, 6), (7, 10), (5, 11), (0, 11)],
        ],
    ),
    "C": (7, [[(7, 2), (5, 0), (2, 0), (0, 2), (0, 9), (2, 11), (5, 11), (7, 9)]]),
    "D": (7, [[(0, 0), (0, 11), (4, 11), (7, 8), (7, 3), (4, 0), (0, 0)]]),
    "E": (7, [[(7, 0), (0, 0), (0, 11), (7, 11)], [(0, 5), (5, 5)]]),
    "F": (7, [[(7, 0), (0, 0), (0, 11)], [(0, 5), (5, 5)]]),
    "G": (
        7,
        [[(7, 2), (5, 0), (2, 0), (0, 2), (0, 9), (2, 11), (5, 11), (7, 9), (7, 6), (4, 6)]],
    ),
    "H": (7, [[(0, 0), (0, 11)], [(7, 0), (7, 11)], [(0, 5), (7, 5)]]),
    "I": (4, [[(0, 0), (4, 0)], [(2, 0), (2, 11)], [(0, 11), (4, 11)]]),
    "J": (6, [[(2, 0), (6, 0), (6, 9), (4, 11), (2, 11), (0, 9)]]),
    "K": (7, [[(0, 0), (0, 11)], [(7, 0), (0, 6), (7, 11)]]),
    "L": (7, [[(0, 0), (0, 11), (7, 11)]]),
    "M": (7, [[(0, 11), (0, 0), (3, 6), (4, 6), (7, 0), (7, 11)]]),
    "N": (7, [[(0, 11), (0, 0), (7, 11), (7, 0)]]),
    "O": (7, [[(2, 0), (5, 0), (7, 2), (7, 9), (5, 11), (2, 11), (0, 9), (0, 2), (2, 0)]]),
    "P": (7, [[(0, 11), (0, 0), (5, 0), (7, 2), (7, 4), (5, 6), (0, 6)]]),
    "Q": (
        7,
        [
            [(2, 0), (5, 0), (7, 2), (7, 9), (5, 11), (2, 11), (0, 9), (0, 2), (2, 0)],
            [(4, 8), (7, 11)],
        ],
    ),
    "R": (
        7,
        [[(0, 11), (0, 0), (5, 0), (7, 2), (7, 4), (5, 6), (0, 6)], [(4, 6), (7, 11)]],
    ),
    "S": (
        7,
        [[(7, 2), (5, 0), (2, 0), (0, 2), (0, 4), (2, 5), (5, 6), (7, 7), (7, 9), (5, 11), (2, 11), (0, 9)]],
    ),
    "T": (6, [[(0, 0), (6, 0)], [(3, 0), (3, 11)]]),
    "U": (7, [[(0, 0), (0, 9), (2, 11), (5, 11), (7, 9), (7, 0)]]),
    "V": (6, [[(0, 0), (3, 11), (6, 0)]]),
    "W": (7, [[(0, 0), (1, 11), (3, 5), (4, 5), (6, 11), (7, 0)]]),
    "X": (7, [[(0, 0), (7, 11)], [(7, 0), (0, 11)]]),
    "Y": (6, [[(0, 0), (3, 5), (6, 0)], [(3, 5), (3, 11)]]),
    "Z": (7, [[(0, 0), (7, 0), (0, 11), (7, 11)]]),
    "0": (
        7,
        [
            [(2, 0), (5, 0), (7, 2), (7, 9), (5, 11), (2, 11), (0, 9), (0, 2), (2, 0)],
            [(1, 9), (6, 2)],
        ],
    ),
    "1": (4, [[(0, 2), (2, 0), (2, 11)], [(0, 11), (4, 11)]]),
    "2": (7, [[(0, 2), (2, 0), (5, 0), (7, 2), (7, 4), (0, 11), (7, 11)]]),
    "3": (
        7,
        [
            [(0, 2), (2, 0), (5, 0), (7, 2), (7, 4), (5, 5), (3, 5)],
            [(5, 5), (7, 7), (7, 9), (5, 11), (2, 11), (0, 9)],
        ],
    ),
    "4": (7, [[(5, 11), (5, 0), (0, 7), (7, 7)]]),
    "5": (7, [[(7, 0), (0, 0), (0, 5), (5, 5), (7, 7), (7, 9), (5, 11), (2, 11), (0, 9)]]),
    "6": (
        7,
        [[(6, 1), (4, 0), (2, 0), (0, 2), (0, 9), (2, 11), (5, 11), (7, 9), (7, 7), (5, 5), (0, 5)]],
    ),
    "7": (7, [[(0, 0), (7, 0), (2, 11)]]),
    "8": (
        7,
        [
            [(2, 5), (0, 4), (0, 2), (2, 0), (5, 0), (7, 2), (7, 4), (5, 5), (2, 5)],
            [(2, 5), (0, 7), (0, 9), (2, 11), (5, 11), (7, 9), (7, 7), (5, 5)],
        ],
    ),
    "9": (
        7,
        [[(7, 6), (2, 6), (0, 4), (0, 2), (2, 0), (5, 0), (7, 2), (7, 9), (5, 11), (3, 11), (1, 10)]],
    ),
    " ": (4, []),
    ".": (2, [[(1, 10), (1, 11)]]),
    ",": (2, [[(1, 9), (1, 10), (0, 12)]]),
    ":": (2, [[(1, 3), (1, 4)], [(1, 9), (1, 10)]]),
    ";": (2, [[(1, 3), (1, 4)], [(1, 9), (1, 10), (0, 12)]]),
    "'": (2, [[(1, 0), (1, 3)]]),
    "-": (5, [[(0, 6), (5, 6)]]),
    "/": (5, [[(5, 0), (0, 11)]]),
    "(": (3, [[(3, 0), (1, 3), (1, 8), (3, 11)]]),
    ")": (3, [[(0, 0), (2, 3), (2, 8), (0, 11)]]),
    "%": (
        7,
        [
            [(0, 1), (2, 1), (2, 3), (0, 3), (0, 1)],
            [(7, 0), (0, 11)],
            [(5, 8), (7, 8), (7, 10), (5, 10), (5, 8)],
        ],
    ),
    "$": (
        6,
        [
            [(6, 2), (4, 1), (2, 1), (0, 2), (0, 4), (2, 5), (4, 6), (6, 7), (6, 9), (4, 10), (2, 10), (0, 9)],
            [(3, 0), (3, 11)],
        ],
    ),
    "&": (7, [[(7, 11), (1, 4), (1, 1), (3, 0), (5, 1), (5, 3), (0, 8), (0, 10), (2, 11), (5, 11), (7, 8)]]),
    "+": (6, [[(3, 2), (3, 9)], [(0, 5), (6, 5)]]),
    "!": (2, [[(1, 0), (1, 7)], [(1, 10), (1, 11)]]),
    "?": (6, [[(0, 2), (2, 0), (4, 0), (6, 2), (6, 4), (3, 6), (3, 8)], [(3, 10), (3, 11)]]),
    "\u2022": (4, [[(2, 4), (3, 5), (2, 6), (1, 5), (2, 4)]]),
}

GLYPH_GAP = 2


def measure_text(text: str, scale: int = 1, gap: int = GLYPH_GAP) -> int:
    """Return total pixel width of text rendered at integer scale."""
    if not text:
        return 0
    total = 0
    for idx, ch in enumerate(text):
        adv = FONT_GLYPHS.get(ch, FONT_GLYPHS[" "])[0]
        total += adv * scale
        if idx < len(text) - 1:
            total += gap * scale
    return total


def wrap_text(text: str, max_width: int, scale: int = 1, max_lines: int = 2) -> list[str]:
    """Greedy word-wrap text to fit within max_width at integer scale."""
    words = text.split(" ")
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = word if not current else f"{current} {word}"
        if measure_text(candidate, scale) <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines[:max_lines]


def draw_text(
    canvas: Canvas,
    x: int,
    y: int,
    text: str,
    color: Color,
    scale: int = 1,
    thickness: int = 1,
    gap: int = GLYPH_GAP,
) -> None:
    """Render uppercase stroke-vector text onto canvas."""
    cursor_x = x
    for ch in text:
        adv, strokes = FONT_GLYPHS.get(ch, FONT_GLYPHS[" "])
        for poly in strokes:
            for i in range(len(poly) - 1):
                x0 = cursor_x + poly[i][0] * scale
                y0 = y + poly[i][1] * scale
                x1 = cursor_x + poly[i + 1][0] * scale
                y1 = y + poly[i + 1][1] * scale
                canvas.draw_line(x0, y0, x1, y1, color, thickness)
        cursor_x += (adv + gap) * scale


def draw_centered_text(
    canvas: Canvas,
    cx: int,
    y: int,
    text: str,
    color: Color,
    scale: int = 1,
    thickness: int = 1,
) -> None:
    """Draw text horizontally centered around cx."""
    w = measure_text(text, scale)
    draw_text(canvas, cx - w // 2, y, text, color, scale, thickness)


FOOTER_TEXT = (
    "JAPAN SCRAMBLES JETS AFTER SUSPECTED RUSSIAN AIRSPACE VIOLATION  \u2022  "
    "VULCAN ROCKET LOST WITH 40 AMAZON SATELLITES  \u2022  "
    "COP31 DRAFT URGES FASTER FOSSIL-FUEL EXIT  \u2022  "
    "FIVE EU STATES TALK RWANDA DEPORTATION CENTRE"
)


def draw_masthead(canvas: Canvas) -> None:
    """Draw the newspaper masthead band (y=20..186)."""
    cx = WIDTH // 2
    canvas.fill_rect(28, 20, WIDTH - 56, 4, INK)
    canvas.fill_rect(28, 28, WIDTH - 56, 1, INK)

    overline = "THE WORLD IN ONE IMAGE"
    over_w = measure_text(overline, scale=2)
    draw_centered_text(canvas, cx, 40, overline, RED_ACCENT, scale=2, thickness=3)
    rule_left_end = cx - over_w // 2 - 18
    rule_right_start = cx + over_w // 2 + 18
    canvas.fill_rect(28, 50, rule_left_end - 28, 2, RULE_COLOR)
    canvas.fill_rect(rule_right_start, 50, WIDTH - 28 - rule_right_start, 2, RULE_COLOR)

    title = "TUESDAY 17 NOVEMBER 2026"
    draw_centered_text(canvas, cx, 78, title, INK, scale=4, thickness=6)

    subline = "SIX STORIES THAT DEFINED THE DAY"
    draw_centered_text(canvas, cx, 142, subline, BLUE_ACCENT, scale=2, thickness=2)

    canvas.fill_rect(28, 178, WIDTH - 56, 3, INK)
    canvas.fill_rect(28, 184, WIDTH - 56, 1, INK)


def draw_footer(canvas: Canvas) -> None:
    """Draw the bottom ticker strip (y=948..1006)."""
    fx, fy, fw, fh = 28, 948, WIDTH - 56, 58
    canvas.fill_rect(fx, fy, fw, fh, BLUE_ACCENT)
    canvas.fill_rect(fx, fy, fw, 3, RED_ACCENT)

    parts = FOOTER_TEXT.split("  \u2022  ")
    line1 = f"{parts[0]}  \u2022  {parts[1]}"
    line2 = f"{parts[2]}  \u2022  {parts[3]}"
    draw_centered_text(canvas, WIDTH // 2, fy + 14, line1, WHITE, scale=1, thickness=2)
    draw_centered_text(canvas, WIDTH // 2, fy + 34, line2, WHITE, scale=1, thickness=2)


PANELS: list[dict[str, str]] = [
    {
        "kicker": "MARKETS",
        "headline": "NASDAQ INTO CORRECTION",
        "deck": "NASDAQ -2.5%, S&P 500 -1.9%, DOW -1.4%; BRENT -3.6% TO $92.44; GOLD AT 13-MONTH LOW",
        "icon": "markets",
    },
    {
        "kicker": "UKRAINE",
        "headline": "CRIMEA BRIDGE HIT IN HUGE DRONE RAID",
        "deck": "MASS OVERNIGHT BARRAGE CLOSES THE BRIDGE; RUSSIA STRIKES KYIV BRIDGES",
        "icon": "ukraine",
    },
    {
        "kicker": "SUMMIT",
        "headline": "XI, TRUMP, PUTIN TO MEET IN SHENZHEN",
        "deck": "CHINA CONFIRMS FIRST TRILATERAL SUMMIT, 19 NOVEMBER",
        "icon": "summit",
    },
    {
        "kicker": "CYBERATTACK",
        "headline": "178 SITES HIT IN SUPPLY-CHAIN HACK",
        "deck": "MALICIOUS CODE VIA OPTIMIZELY TARGETS BBC, CNN, ZOOM, HSBC",
        "icon": "cyber",
    },
    {
        "kicker": "HORMUZ",
        "headline": "TANKER ATTACKED IN STRAIT OF HORMUZ",
        "deck": "ENGINE-ROOM FIRE AFTER ATTACK REPORTED BY UKMTO",
        "icon": "hormuz",
    },
    {
        "kicker": "AIR TRAVEL",
        "headline": "FAA HALTS ROUTER ROLLOUT AFTER AIR CHAOS",
        "deck": "1M+ STRANDED IN NATIONWIDE GROUND STOP; CAUSE UNCLEAR",
        "icon": "air",
    },
]


def _draw_star(canvas: Canvas, cx: int, cy: int, r_outer: float, color: Color) -> None:
    """Draw a filled 5-pointed star centered at (cx, cy)."""
    r_inner = r_outer * 0.4
    pts: list[Point] = []
    for i in range(10):
        angle = -math.pi / 2 + i * math.pi / 5
        r = r_outer if i % 2 == 0 else r_inner
        pts.append((cx + r * math.cos(angle), cy + r * math.sin(angle)))
    canvas.fill_polygon(pts, color)


def _draw_warning_triangle(
    canvas: Canvas, cx: int, cy: int, size: int, fill: Color, border: Color
) -> None:
    """Draw a warning triangle with an exclamation mark."""
    half = size // 2
    top_y = cy - half
    bot_y = cy + half - 2
    canvas.fill_polygon([(cx, top_y), (cx - half, bot_y), (cx + half, bot_y)], border)
    inner = max(4, half - 4)
    canvas.fill_polygon(
        [(cx, top_y + 6), (cx - inner, bot_y - 3), (cx + inner, bot_y - 3)], fill
    )
    canvas.fill_rect(cx - 2, top_y + size // 3, 4, max(6, size // 3), border)
    canvas.fill_rect(cx - 2, bot_y - 9, 4, 4, border)


def _draw_icon_markets(canvas: Canvas, ix: int, iy: int, iw: int, ih: int) -> None:
    """Falling line chart with red arrow."""
    for gy in (iy + 24, iy + 48, iy + 72):
        canvas.fill_rect(ix + 24, gy, iw - 96, 1, RULE_COLOR)
    canvas.fill_rect(ix + 24, iy + 14, 2, ih - 26, INK)
    canvas.fill_rect(ix + 24, iy + ih - 14, iw - 96, 2, INK)

    pts = [
        (ix + 32, iy + 22),
        (ix + 82, iy + 30),
        (ix + 118, iy + 24),
        (ix + 166, iy + 48),
        (ix + 206, iy + 40),
        (ix + 258, iy + 66),
        (ix + 296, iy + 58),
        (ix + 344, iy + 80),
    ]
    for i in range(len(pts) - 1):
        canvas.draw_line(pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1], RED_ACCENT, 4)
    for px, py in pts:
        canvas.fill_circle(px, py, 4, BLUE_ACCENT)

    # Large downward red arrow on the right
    ax = ix + iw - 42
    canvas.fill_rect(ax - 4, iy + 16, 8, 42, RED_ACCENT)
    canvas.fill_polygon([(ax - 16, iy + 54), (ax + 16, iy + 54), (ax, iy + 82)], RED_ACCENT)


def _draw_icon_ukraine(canvas: Canvas, ix: int, iy: int, iw: int, ih: int) -> None:
    """Bridge silhouette with drone shapes above."""
    water_y = iy + ih - 22
    canvas.fill_rect(ix + 4, water_y, iw - 8, 18, BLUE_ACCENT)
    for wx in range(ix + 20, ix + iw - 30, 48):
        canvas.fill_rect(wx, water_y + 7, 24, 2, WHITE)

    # Bridge piers and deck
    deck_y = iy + 54
    canvas.fill_rect(ix + 18, deck_y, iw - 36, 7, INK)
    for px in (ix + 64, ix + 152, ix + 284, ix + 372):
        canvas.fill_rect(px - 6, deck_y + 7, 12, water_y - deck_y - 7, INK)
    # Central arch truss
    arch_pts = [
        (ix + 152, deck_y),
        (ix + 178, iy + 28),
        (ix + 258, iy + 28),
        (ix + 284, deck_y),
    ]
    for i in range(len(arch_pts) - 1):
        canvas.draw_line(
            arch_pts[i][0], arch_pts[i][1], arch_pts[i + 1][0], arch_pts[i + 1][1], INK, 4
        )
    for sx in (ix + 186, ix + 218, ix + 250):
        canvas.fill_rect(sx, iy + 30, 2, deck_y - (iy + 30), INK)

    # Three drones above + explosion burst on the bridge deck at the strike point
    for dx, dy in ((ix + 96, iy + 18), (ix + 218, iy + 14), (ix + 340, iy + 22)):
        canvas.fill_polygon([(dx - 16, dy), (dx + 16, dy), (dx, dy + 7)], INK)
        canvas.fill_rect(dx - 3, dy - 4, 6, 12, INK)
        canvas.fill_rect(dx - 18, dy - 3, 6, 2, RED_ACCENT)
        canvas.fill_rect(dx + 12, dy - 3, 6, 2, RED_ACCENT)
    bx, by = ix + 218, deck_y - 4
    outer_pts: list[Point] = []
    inner_pts: list[Point] = []
    for i in range(18):
        angle = -math.pi / 2 + i * math.pi / 9
        r_out = 11.0 if i % 2 == 0 else 4.5
        r_in = 7.0 if i % 2 == 0 else 2.8
        outer_pts.append((bx + r_out * math.cos(angle), by + r_out * math.sin(angle)))
        inner_pts.append((bx + r_in * math.cos(angle), by + r_in * math.sin(angle)))
    canvas.fill_polygon(outer_pts, RED_ACCENT)
    canvas.fill_polygon(inner_pts, (235, 118, 30))


def _draw_icon_summit(canvas: Canvas, ix: int, iy: int, iw: int, ih: int) -> None:
    """Three small flags (China, USA, Russia) side by side."""
    fw, fh = 104, 68
    gap = 28
    start_x = ix + (iw - (3 * fw + 2 * gap)) // 2
    fy = iy + (ih - fh) // 2

    # 1. China flag
    x1 = start_x
    canvas.fill_rect(x1, fy, fw, fh, RED_ACCENT)
    _draw_star(canvas, x1 + 20, fy + 20, 10, GOLD_ACCENT)
    for sx, sy in ((x1 + 36, fy + 10), (x1 + 41, fy + 18), (x1 + 40, fy + 27), (x1 + 34, fy + 34)):
        _draw_star(canvas, sx, sy, 4, GOLD_ACCENT)
    canvas.stroke_rect(x1, fy, fw, fh, INK, 1)

    # 2. USA flag
    x2 = start_x + fw + gap
    canvas.fill_rect(x2, fy, fw, fh, WHITE)
    stripe_h = fh / 13.0
    for s in range(0, 13, 2):
        sy0 = fy + int(round(s * stripe_h))
        sy1 = fy + int(round((s + 1) * stripe_h))
        canvas.fill_rect(x2, sy0, fw, max(1, sy1 - sy0), RED_ACCENT)
    cw, ch = 46, int(round(7 * stripe_h))
    canvas.fill_rect(x2, fy, cw, ch, BLUE_ACCENT)
    for r in range(4):
        for c in range(5):
            canvas.fill_rect(x2 + 5 + c * 8, fy + 4 + r * 8, 3, 3, WHITE)
    canvas.stroke_rect(x2, fy, fw, fh, INK, 1)

    # 3. Russia flag
    x3 = start_x + 2 * (fw + gap)
    band = fh // 3
    canvas.fill_rect(x3, fy, fw, band, WHITE)
    canvas.fill_rect(x3, fy + band, fw, band, BLUE_ACCENT)
    canvas.fill_rect(x3, fy + 2 * band, fw, fh - 2 * band, RED_ACCENT)
    canvas.stroke_rect(x3, fy, fw, fh, INK, 1)


def _draw_icon_cyber(canvas: Canvas, ix: int, iy: int, iw: int, ih: int) -> None:
    """Monitor with warning triangle and bug/shield motif."""
    mx, my, mw, mh = ix + 56, iy + 12, 132, 66
    canvas.fill_rect(mx, my, mw, mh, INK)
    canvas.fill_rect(mx + 6, my + 6, mw - 12, mh - 14, BLUE_ACCENT)
    canvas.fill_rect(mx + mw // 2 - 10, my + mh, 20, 10, INK)
    canvas.fill_rect(mx + mw // 2 - 28, my + mh + 10, 56, 5, INK)
    _draw_warning_triangle(canvas, mx + mw // 2, my + 31, 36, GOLD_ACCENT, RED_ACCENT)

    # Connection line with circuit nodes
    canvas.draw_line(mx + mw + 10, iy + 46, ix + 268, iy + 46, RED_ACCENT, 3)
    canvas.fill_circle(mx + mw + 10, iy + 46, 4, RED_ACCENT)
    canvas.fill_circle(ix + 268, iy + 46, 4, RED_ACCENT)

    # Shield + bug motif on the right
    sx, sy = ix + 318, iy + 48
    canvas.fill_polygon(
        [(sx - 34, sy - 32), (sx + 34, sy - 32), (sx + 30, sy + 6), (sx, sy + 36), (sx - 30, sy + 6)],
        BLUE_ACCENT,
    )
    # Bug silhouette centered on shield
    canvas.fill_circle(sx, sy + 4, 13, RED_ACCENT)
    canvas.fill_circle(sx, sy - 11, 7, INK)
    canvas.draw_line(sx - 3, sy - 16, sx - 9, sy - 23, INK, 2)
    canvas.draw_line(sx + 3, sy - 16, sx + 9, sy - 23, INK, 2)
    for dy in (-4, 4, 12):
        canvas.draw_line(sx - 20, sy + dy - 3, sx - 10, sy + dy, INK, 2)
        canvas.draw_line(sx + 10, sy + dy, sx + 20, sy + dy - 3, INK, 2)


def _draw_icon_hormuz(canvas: Canvas, ix: int, iy: int, iw: int, ih: int) -> None:
    """Oil tanker silhouette with flame and waves."""
    water_y = iy + ih - 20
    canvas.fill_rect(ix + 4, water_y, iw - 8, 16, BLUE_ACCENT)
    for wx in range(ix + 16, ix + iw - 28, 44):
        canvas.fill_polygon([(wx, water_y), (wx + 12, water_y - 5), (wx + 24, water_y)], BLUE_ACCENT)
        canvas.fill_rect(wx + 6, water_y + 7, 20, 2, WHITE)

    # Tanker hull
    hx = ix + 86
    canvas.fill_polygon(
        [(hx, water_y), (hx + 12, water_y - 20), (hx + 248, water_y - 20), (hx + 272, water_y - 29), (hx + 258, water_y)],
        INK,
    )
    # Stern bridge superstructure
    canvas.fill_rect(hx + 22, water_y - 38, 36, 18, INK)
    canvas.fill_rect(hx + 28, water_y - 33, 24, 4, WHITE)

    # Engine-room fire flame + smoke contained inside icon box
    fx, fy = hx + 46, water_y - 38
    canvas.fill_polygon([(fx - 21, fy), (fx - 10, fy - 32), (fx + 4, fy - 20), (fx + 18, fy - 37), (fx + 27, fy)], RED_ACCENT)
    canvas.fill_polygon([(fx - 11, fy), (fx + 3, fy - 22), (fx + 15, fy)], GOLD_ACCENT)
    canvas.fill_circle(fx + 26, fy - 28, 5, MUTED_INK)
    canvas.fill_circle(fx + 38, fy - 32, 6, RULE_COLOR)


def _draw_icon_air(canvas: Canvas, ix: int, iy: int, iw: int, ih: int) -> None:
    """Airplane silhouette with warning triangle."""
    ax, ay = ix + 150, iy + 50
    # Fuselage
    canvas.fill_polygon(
        [(ax - 88, ay - 6), (ax + 68, ay - 6), (ax + 92, ay), (ax + 68, ay + 6), (ax - 88, ay + 6)],
        BLUE_ACCENT,
    )
    # Swept wings + engine pods
    canvas.fill_polygon([(ax - 12, ay - 4), (ax + 18, ay - 4), (ax - 18, ay - 36), (ax - 34, ay - 36)], BLUE_ACCENT)
    canvas.fill_polygon([(ax - 12, ay + 4), (ax + 18, ay + 4), (ax - 18, ay + 36), (ax - 34, ay + 36)], BLUE_ACCENT)
    canvas.fill_rect(ax - 8, ay - 20, 14, 5, INK)
    canvas.fill_rect(ax - 8, ay + 15, 14, 5, INK)
    # Tail fin
    canvas.fill_polygon([(ax - 84, ay - 4), (ax - 62, ay - 4), (ax - 78, ay - 24), (ax - 92, ay - 24)], BLUE_ACCENT)

    # Warning triangle on right
    _draw_warning_triangle(canvas, ix + 340, iy + 50, 62, GOLD_ACCENT, RED_ACCENT)


ICON_DRAWERS = {
    "markets": _draw_icon_markets,
    "ukraine": _draw_icon_ukraine,
    "summit": _draw_icon_summit,
    "cyber": _draw_icon_cyber,
    "hormuz": _draw_icon_hormuz,
    "air": _draw_icon_air,
}


def draw_panel(canvas: Canvas, x: int, y: int, w: int, h: int, panel: dict[str, str]) -> None:
    """Draw a single story panel with kicker, headline, deck, and icon zone."""
    canvas.fill_rect(x, y, w, h, CARD_BG)
    canvas.stroke_rect(x, y, w, h, RULE_COLOR, 1)
    canvas.fill_rect(x, y, w, 4, BLUE_ACCENT)

    pad_x = 16
    text_w = w - 2 * pad_x

    # Kicker in small red caps
    canvas.fill_rect(x + pad_x, y + 14, 8, 10, RED_ACCENT)
    draw_text(canvas, x + pad_x + 14, y + 13, panel["kicker"], RED_ACCENT, scale=1, thickness=2)

    # Headline in large bold caps (2 lines max)
    hl_lines = wrap_text(panel["headline"], text_w, scale=2, max_lines=2)
    hy = y + 32
    for line in hl_lines:
        draw_text(canvas, x + pad_x, hy, line, INK, scale=2, thickness=3)
        hy += 28

    # Deck in smaller caps (2 lines max)
    dk_lines = wrap_text(panel["deck"], text_w, scale=1, max_lines=2)
    dy = y + 92
    for line in dk_lines:
        draw_text(canvas, x + pad_x, dy, line, MUTED_INK, scale=1, thickness=1)
        dy += 16

    # Dedicated icon zone
    ix = x + pad_x
    iy = y + 128
    iw = text_w
    ih = h - 138
    canvas.fill_rect(ix, iy, iw, ih, ICON_BG)
    canvas.stroke_rect(ix, iy, iw, ih, RULE_COLOR, 1)
    ICON_DRAWERS[panel["icon"]](canvas, ix, iy, iw, ih)


def render_poster() -> Canvas:
    """Render the 1024x1024 news poster onto a Canvas."""
    canvas = Canvas(WIDTH, HEIGHT, PAPER_BG)
    draw_masthead(canvas)

    col_w = 474
    row_h = 236
    col_x = (28, 522)
    row_y = (196, 448, 700)
    for idx, panel in enumerate(PANELS):
        c = idx % 2
        r = idx // 2
        draw_panel(canvas, col_x[c], row_y[r], col_w, row_h, panel)

    draw_footer(canvas)
    return canvas


def main() -> None:
    output_dir = os.environ.get("MAKEFUN_OUTPUT_DIR") or "/output"
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "entry.png")

    canvas = render_poster()
    png_bytes = canvas.to_png_bytes()
    with open(output_path, "wb") as f:
        f.write(png_bytes)


if __name__ == "__main__":
    main()
