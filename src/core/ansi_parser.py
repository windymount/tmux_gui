"""Lightweight ANSI SGR escape sequence parser.

Parses only Select Graphic Rendition (ESC[...m) codes for rendering colored
pane content in Qt text widgets. Does NOT handle cursor movement, screen
clearing, or other terminal control sequences.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Standard 8 ANSI colors — xterm-256color default palette
ANSI_COLORS = [
    "#000000",  # 0 black
    "#800000",  # 1 red (maroon)
    "#008000",  # 2 green
    "#808000",  # 3 yellow (olive)
    "#000080",  # 4 blue (navy)
    "#800080",  # 5 magenta (purple)
    "#008080",  # 6 cyan (teal)
    "#c0c0c0",  # 7 white (silver)
]

# Bright variants — xterm-256color defaults
ANSI_BRIGHT_COLORS = [
    "#808080",  # 8  bright black (gray)
    "#ff0000",  # 9  bright red
    "#00ff00",  # 10 bright green
    "#ffff00",  # 11 bright yellow
    "#0000ff",  # 12 bright blue
    "#ff00ff",  # 13 bright magenta
    "#00ffff",  # 14 bright cyan
    "#ffffff",  # 15 bright white
]

# Regex matching ESC[ ... m  (SGR sequence)
_SGR_RE = re.compile(r"\x1b\[([\d;]*)m")

# Regex matching any CSI sequence (for stripping non-SGR escapes)
_CSI_RE = re.compile(r"\x1b\[[\d;]*[A-Za-z]")


@dataclass
class TextStyle:
    """Accumulated text style state."""

    fg: str | None = None  # hex color or None (default)
    bg: str | None = None
    bold: bool = False
    dim: bool = False
    italic: bool = False
    underline: bool = False
    strikethrough: bool = False
    reverse: bool = False

    def reset(self) -> None:
        self.fg = None
        self.bg = None
        self.bold = False
        self.dim = False
        self.italic = False
        self.underline = False
        self.strikethrough = False
        self.reverse = False

    def copy(self) -> TextStyle:
        return TextStyle(
            fg=self.fg, bg=self.bg, bold=self.bold, dim=self.dim,
            italic=self.italic, underline=self.underline,
            strikethrough=self.strikethrough, reverse=self.reverse,
        )


@dataclass
class StyledSpan:
    """A run of text with uniform styling."""

    text: str
    style: TextStyle


def strip_ansi(text: str) -> str:
    """Remove all ANSI CSI escape sequences from *text*."""
    return _CSI_RE.sub("", text)


def parse_ansi(text: str) -> list[StyledSpan]:
    """Parse *text* containing ANSI SGR sequences into styled spans."""
    # Strip non-SGR CSI sequences (cursor movement, erase, etc.) so they
    # don't leak as garbled text. Matches CSI ending in any letter except 'm'.
    text = re.sub(r"\x1b\[[\d;]*[A-LN-Za-ln-z]", "", text)
    spans: list[StyledSpan] = []
    style = TextStyle()
    pos = 0

    for m in _SGR_RE.finditer(text):
        # Text before this escape sequence
        if m.start() > pos:
            spans.append(StyledSpan(text=text[pos:m.start()], style=style.copy()))

        # Apply SGR codes
        codes_str = m.group(1)
        codes = [int(c) for c in codes_str.split(";") if c] if codes_str else [0]
        _apply_sgr(style, codes)
        pos = m.end()

    # Remaining text after last escape
    if pos < len(text):
        spans.append(StyledSpan(text=text[pos:], style=style.copy()))

    return spans


def _apply_sgr(style: TextStyle, codes: list[int]) -> None:
    """Apply a list of SGR parameter codes to *style*."""
    i = 0
    while i < len(codes):
        c = codes[i]

        if c == 0:
            style.reset()
        elif c == 1:
            style.bold = True
        elif c == 2:
            style.dim = True
        elif c == 3:
            style.italic = True
        elif c == 4:
            style.underline = True
        elif c == 7:
            style.reverse = True
        elif c == 9:
            style.strikethrough = True
        elif c == 22:
            style.bold = False
            style.dim = False
        elif c == 23:
            style.italic = False
        elif c == 24:
            style.underline = False
        elif c == 27:
            style.reverse = False
        elif c == 29:
            style.strikethrough = False

        # Standard foreground 30-37
        elif 30 <= c <= 37:
            style.fg = ANSI_COLORS[c - 30]
        elif c == 39:
            style.fg = None  # default

        # Standard background 40-47
        elif 40 <= c <= 47:
            style.bg = ANSI_COLORS[c - 40]
        elif c == 49:
            style.bg = None  # default

        # Bright foreground 90-97
        elif 90 <= c <= 97:
            style.fg = ANSI_BRIGHT_COLORS[c - 90]

        # Bright background 100-107
        elif 100 <= c <= 107:
            style.bg = ANSI_BRIGHT_COLORS[c - 100]

        # Extended color: 38;5;N (256-color) or 38;2;R;G;B (24-bit)
        elif c == 38:
            color, consumed = _parse_extended_color(codes, i + 1)
            if color:
                style.fg = color
            i += consumed

        elif c == 48:
            color, consumed = _parse_extended_color(codes, i + 1)
            if color:
                style.bg = color
            i += consumed

        i += 1


def _parse_extended_color(codes: list[int], start: int) -> tuple[str | None, int]:
    """Parse 256-color (5;N) or 24-bit (2;R;G;B) color starting at *start*."""
    if start >= len(codes):
        return None, 0

    mode = codes[start]

    if mode == 5 and start + 1 < len(codes):
        # 256-color
        n = codes[start + 1]
        return _color_256(n), 2

    if mode == 2 and start + 3 < len(codes):
        # 24-bit RGB
        r, g, b = codes[start + 1], codes[start + 2], codes[start + 3]
        return f"#{r:02x}{g:02x}{b:02x}", 4

    return None, 1


# xterm 6x6x6 color cube intensity values (indices 0-5)
_CUBE_VALUES = [0x00, 0x5f, 0x87, 0xaf, 0xd7, 0xff]


def _color_256(n: int) -> str:
    """Convert a 256-color index to a hex color string (xterm-256color)."""
    if n < 8:
        return ANSI_COLORS[n]
    if n < 16:
        return ANSI_BRIGHT_COLORS[n - 8]

    # 216-color cube: 16-231, using xterm intensity values
    if n < 232:
        n -= 16
        b = _CUBE_VALUES[n % 6]
        g = _CUBE_VALUES[(n // 6) % 6]
        r = _CUBE_VALUES[n // 36]
        return f"#{r:02x}{g:02x}{b:02x}"

    # Grayscale ramp: 232-255
    v = 8 + (n - 232) * 10
    return f"#{v:02x}{v:02x}{v:02x}"
