"""Tests for config load/save round-trip."""

from pathlib import Path

from src.core.config import AppConfig, ConnectionConfig, PollConfig


class TestConfigRoundTrip:
    def test_save_and_load(self, tmp_path: Path):
        path = tmp_path / "config.json"
        cfg = AppConfig(
            connections=[
                ConnectionConfig(name="srv1", host="10.0.0.1", port=2222, username="admin"),
                ConnectionConfig(name="srv2", host="example.com"),
            ],
            poll=PollConfig(structure_interval_ms=5000),
            font_family="Fira Code",
            font_size=12,
            theme="dark",
        )
        cfg.save(path)

        loaded = AppConfig.load(path)
        assert len(loaded.connections) == 2
        assert loaded.connections[0].name == "srv1"
        assert loaded.connections[0].port == 2222
        assert loaded.connections[1].host == "example.com"
        assert loaded.poll.structure_interval_ms == 5000
        assert loaded.font_family == "Fira Code"
        assert loaded.font_size == 12
        assert loaded.theme == "dark"

    def test_load_missing_file(self, tmp_path: Path):
        path = tmp_path / "nonexistent.json"
        cfg = AppConfig.load(path)
        assert len(cfg.connections) == 0
        assert cfg.font_size == 10  # default

    def test_load_corrupt_file(self, tmp_path: Path):
        path = tmp_path / "bad.json"
        path.write_text("not json!!!")
        cfg = AppConfig.load(path)
        assert len(cfg.connections) == 0  # falls back to defaults

    def test_connection_helpers(self):
        cfg = AppConfig()
        conn = ConnectionConfig(name="test", host="localhost")
        cfg.add_connection(conn)
        assert cfg.find_connection("test") is conn
        cfg.remove_connection("test")
        assert cfg.find_connection("test") is None
