"""Tests for the ANSI SGR escape sequence parser."""


from src.core.ansi_parser import _color_256, parse_ansi


class TestParseAnsi:
    """Test parse_ansi() with various SGR sequences."""

    def test_plain_text(self):
        spans = parse_ansi("hello world")
        assert len(spans) == 1
        assert spans[0].text == "hello world"
        assert spans[0].style.fg is None
        assert spans[0].style.bold is False

    def test_single_color(self):
        # Red foreground: ESC[31m starts at pos 0, so no span before it
        spans = parse_ansi("\x1b[31mhello\x1b[0m world")
        assert len(spans) == 2
        assert spans[0].text == "hello"
        assert spans[0].style.fg == "#CC0000"  # red
        assert spans[1].text == " world"
        assert spans[1].style.fg is None  # reset

    def test_bold(self):
        spans = parse_ansi("\x1b[1mbold text\x1b[0m")
        assert spans[0].text == "bold text"
        assert spans[0].style.bold is True

    def test_combined_attributes(self):
        # Bold + green foreground
        spans = parse_ansi("\x1b[1;32mOK\x1b[0m")
        assert spans[0].text == "OK"
        assert spans[0].style.bold is True
        assert spans[0].style.fg == "#00CC00"

    def test_256_color(self):
        # 256-color foreground: color index 196 (bright red in the cube)
        spans = parse_ansi("\x1b[38;5;196mred\x1b[0m")
        assert spans[0].text == "red"
        assert spans[0].style.fg is not None

    def test_24bit_color(self):
        spans = parse_ansi("\x1b[38;2;255;128;0morange\x1b[0m")
        assert spans[0].text == "orange"
        assert spans[0].style.fg == "#ff8000"

    def test_background_color(self):
        spans = parse_ansi("\x1b[44mblue bg\x1b[0m")
        assert spans[0].text == "blue bg"
        assert spans[0].style.bg == "#0000CC"

    def test_bright_colors(self):
        spans = parse_ansi("\x1b[91mbright red\x1b[0m")
        assert spans[0].text == "bright red"
        assert spans[0].style.fg == "#FF5555"

    def test_reset_clears_all(self):
        spans = parse_ansi("\x1b[1;4;31mstuff\x1b[0mplain")
        assert spans[0].style.bold is True
        assert spans[0].style.underline is True
        assert spans[0].style.fg == "#CC0000"
        assert spans[1].style.bold is False
        assert spans[1].style.underline is False
        assert spans[1].style.fg is None

    def test_empty_string(self):
        spans = parse_ansi("")
        assert len(spans) == 0

    def test_only_escape_no_text(self):
        spans = parse_ansi("\x1b[31m\x1b[0m")
        # No text between escapes, so no spans
        assert len(spans) == 0


class TestColor256:
    """Test the 256-color lookup function."""

    def test_standard_colors(self):
        assert _color_256(0) == "#000000"
        assert _color_256(1) == "#CC0000"

    def test_bright_colors(self):
        assert _color_256(8) == "#555555"
        assert _color_256(15) == "#FFFFFF"

    def test_color_cube(self):
        # Color 16 = 0,0,0 in the cube
        assert _color_256(16) == "#000000"
        # Color 196 = r=5,g=0,b=0 -> 255,0,0
        assert _color_256(196) == "#ff0000"

    def test_grayscale(self):
        # 232 = darkest gray (8)
        assert _color_256(232) == "#080808"
        # 255 = lightest gray (238)
        assert _color_256(255) == "#eeeeee"
