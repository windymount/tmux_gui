"""Data classes representing tmux server state (sessions, windows, panes)."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TmuxPane:
    """A single tmux pane."""

    pane_id: str  # e.g. "%17"
    pane_index: int
    width: int
    height: int
    top: int
    left: int
    bottom: int
    right: int
    active: bool
    current_command: str
    pid: int
    content: str = ""  # latest capture-pane output


@dataclass
class TmuxWindow:
    """A tmux window containing one or more panes."""

    window_id: str  # e.g. "@15"
    window_index: int
    name: str
    width: int
    height: int
    layout: str  # raw layout string, e.g. "fb21,80x24,0,0{...}"
    active: bool
    pane_count: int
    panes: dict[str, TmuxPane] = field(default_factory=dict)  # keyed by pane_id


@dataclass
class TmuxSession:
    """A tmux session containing one or more windows."""

    session_id: str  # e.g. "$0"
    name: str
    window_count: int
    attached: bool
    windows: dict[str, TmuxWindow] = field(default_factory=dict)  # keyed by window_id


@dataclass
class TmuxState:
    """Full state snapshot of a remote tmux server."""

    host_id: str
    sessions: dict[str, TmuxSession] = field(default_factory=dict)  # keyed by session_id

    @property
    def session_list(self) -> list[TmuxSession]:
        return sorted(self.sessions.values(), key=lambda s: s.name)

    def find_session_by_name(self, name: str) -> TmuxSession | None:
        for s in self.sessions.values():
            if s.name == name:
                return s
        return None


# ---------- Layout string parser ----------

@dataclass
class LayoutNode:
    """Recursive tree node representing a tmux pane layout.

    Leaf nodes have ``pane_id`` set and no children.
    Internal nodes have ``split`` set to 'h' (horizontal / stacked) or 'v' (vertical / side-by-side)
    and contain children.
    """

    width: int
    height: int
    x: int
    y: int
    pane_id: int | None = None  # leaf only
    split: str | None = None  # 'h' or 'v', internal only
    children: list[LayoutNode] = field(default_factory=list)

    @property
    def is_leaf(self) -> bool:
        return self.pane_id is not None


def parse_layout(layout_str: str) -> LayoutNode:
    """Parse a tmux layout string into a tree of LayoutNodes.

    Format: ``<checksum>,<body>`` where body is parsed recursively.
    Each node: ``<W>x<H>,<x>,<y>[,<pane_id>]`` optionally followed by
    ``{children}`` (vertical split) or ``[children]`` (horizontal split).

    Examples::

        "fb21,80x24,0,0,17"                           -> single pane (leaf)
        "fb21,80x24,0,0{40x24,0,0,17,39x24,41,0,18}" -> two panes side-by-side
    """
    try:
        # Strip leading checksum (hex digits followed by comma)
        idx = layout_str.index(",")
        body = layout_str[idx + 1:]
        node, _ = _parse_node(body, 0)
    except (ValueError, IndexError) as exc:
        raise ValueError(f"Failed to parse tmux layout: {layout_str!r}") from exc
    return node


def _parse_node(s: str, pos: int) -> tuple[LayoutNode, int]:
    """Parse one node starting at *pos*, return (node, next_pos)."""
    # Parse WxH
    w_end = s.index("x", pos)
    width = int(s[pos:w_end])
    pos = w_end + 1

    # Parse H,x,y
    dims: list[int] = []
    while len(dims) < 3:
        # Find next delimiter: comma, {, [, }, ], or end
        end = pos
        while end < len(s) and s[end] not in ",{}[]":
            end += 1
        dims.append(int(s[pos:end]))
        pos = end
        if len(dims) < 3:
            pos += 1  # skip comma

    height, x, y = dims

    # Check what follows: comma (pane_id), bracket (children), or end/delimiter
    if pos < len(s) and s[pos] == ",":
        # Could be a pane_id or start of next sibling
        # Peek ahead to see if it's a number
        peek = pos + 1
        num_end = peek
        while num_end < len(s) and s[num_end].isdigit():
            num_end += 1
        if num_end > peek and (num_end >= len(s) or s[num_end] in ",{}[]"):
            pane_id = int(s[peek:num_end])
            return LayoutNode(width, height, x, y, pane_id=pane_id), num_end
        # Otherwise it's not a pane_id — fall through to bracket parsing

    if pos < len(s) and s[pos] in "{[":
        open_bracket = s[pos]
        split_type = "v" if open_bracket == "{" else "h"
        close_bracket = "}" if open_bracket == "{" else "]"
        pos += 1  # skip open bracket

        children: list[LayoutNode] = []
        while pos < len(s) and s[pos] != close_bracket:
            if s[pos] == ",":
                pos += 1  # skip comma separator between children
                continue
            child, pos = _parse_node(s, pos)
            children.append(child)

        pos += 1  # skip close bracket
        return LayoutNode(width, height, x, y, split=split_type, children=children), pos

    # Leaf with no pane_id (shouldn't normally happen but be defensive)
    return LayoutNode(width, height, x, y), pos
