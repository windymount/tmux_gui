"""Tests for tmux layout string parser and state data classes."""


from src.core.tmux_state import TmuxSession, TmuxState, parse_layout


class TestLayoutParser:
    """Test parse_layout() against known tmux layout strings."""

    def test_single_pane(self):
        # Single pane: "checksum,80x24,0,0,17"
        node = parse_layout("fb21,80x24,0,0,17")
        assert node.is_leaf
        assert node.width == 80
        assert node.height == 24
        assert node.x == 0
        assert node.y == 0
        assert node.pane_id == 17

    def test_vertical_split_two_panes(self):
        # Two panes side by side (vertical split)
        layout = "fb21,80x24,0,0{40x24,0,0,17,39x24,41,0,18}"
        node = parse_layout(layout)
        assert not node.is_leaf
        assert node.split == "v"
        assert node.width == 80
        assert node.height == 24
        assert len(node.children) == 2

        left = node.children[0]
        assert left.is_leaf
        assert left.width == 40
        assert left.pane_id == 17

        right = node.children[1]
        assert right.is_leaf
        assert right.width == 39
        assert right.pane_id == 18

    def test_horizontal_split_two_panes(self):
        # Two panes stacked (horizontal split)
        layout = "c6a3,80x24,0,0[80x12,0,0,5,80x11,0,13,6]"
        node = parse_layout(layout)
        assert not node.is_leaf
        assert node.split == "h"
        assert len(node.children) == 2

        top = node.children[0]
        assert top.is_leaf
        assert top.height == 12
        assert top.pane_id == 5

        bottom = node.children[1]
        assert bottom.is_leaf
        assert bottom.height == 11
        assert bottom.pane_id == 6

    def test_nested_splits(self):
        # Top pane + bottom split into two side-by-side
        layout = "d5e2,80x24,0,0[80x12,0,0,10,80x11,0,13{40x11,0,13,11,39x11,41,13,12}]"
        node = parse_layout(layout)
        assert node.split == "h"
        assert len(node.children) == 2

        top = node.children[0]
        assert top.is_leaf
        assert top.pane_id == 10

        bottom = node.children[1]
        assert bottom.split == "v"
        assert len(bottom.children) == 2
        assert bottom.children[0].pane_id == 11
        assert bottom.children[1].pane_id == 12

    def test_three_way_vertical(self):
        # Three panes side by side
        layout = "abcd,120x24,0,0{40x24,0,0,1,39x24,41,0,2,39x24,81,0,3}"
        node = parse_layout(layout)
        assert node.split == "v"
        assert len(node.children) == 3
        assert [c.pane_id for c in node.children] == [1, 2, 3]


class TestTmuxState:
    """Test TmuxState helper methods."""

    def test_find_session_by_name(self):
        state = TmuxState(host_id="test")
        s1 = TmuxSession(session_id="$0", name="main", window_count=2, attached=True)
        s2 = TmuxSession(session_id="$1", name="dev", window_count=1, attached=False)
        state.sessions["$0"] = s1
        state.sessions["$1"] = s2

        assert state.find_session_by_name("main") is s1
        assert state.find_session_by_name("dev") is s2
        assert state.find_session_by_name("nonexistent") is None

    def test_session_list_sorted(self):
        state = TmuxState(host_id="test")
        state.sessions["$1"] = TmuxSession("$1", "zebra", 1, False)
        state.sessions["$0"] = TmuxSession("$0", "alpha", 1, False)
        names = [s.name for s in state.session_list]
        assert names == ["alpha", "zebra"]
