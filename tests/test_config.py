"""Tests for config load/save round-trip."""

from pathlib import Path

from src.core.config import AppConfig, ConnectionConfig, PollConfig, parse_ssh_config


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


class TestParseSSHConfig:
    def test_basic_hosts(self, tmp_path: Path):
        ssh_config = tmp_path / "config"
        ssh_config.write_text(
            "Host myserver\n"
            "    HostName 10.0.0.1\n"
            "    User admin\n"
            "    Port 2222\n"
            "    IdentityFile ~/.ssh/id_ed25519\n"
            "\n"
            "Host devbox\n"
            "    HostName dev.example.com\n"
            "    User developer\n"
        )
        hosts = parse_ssh_config(ssh_config)
        assert len(hosts) == 2

        assert hosts[0].name == "myserver"
        assert hosts[0].host == "10.0.0.1"
        assert hosts[0].username == "admin"
        assert hosts[0].port == 2222
        assert "id_ed25519" in hosts[0].key_file

        assert hosts[1].name == "devbox"
        assert hosts[1].host == "dev.example.com"
        assert hosts[1].username == "developer"
        assert hosts[1].port == 22  # default

    def test_skips_wildcard(self, tmp_path: Path):
        ssh_config = tmp_path / "config"
        ssh_config.write_text(
            "Host *\n"
            "    ServerAliveInterval 60\n"
            "\n"
            "Host prod\n"
            "    HostName prod.example.com\n"
        )
        hosts = parse_ssh_config(ssh_config)
        assert len(hosts) == 1
        assert hosts[0].name == "prod"

    def test_skips_no_hostname(self, tmp_path: Path):
        ssh_config = tmp_path / "config"
        ssh_config.write_text(
            "Host alias-only\n"
            "    User someone\n"
        )
        hosts = parse_ssh_config(ssh_config)
        assert len(hosts) == 0

    def test_comments_and_empty_lines(self, tmp_path: Path):
        ssh_config = tmp_path / "config"
        ssh_config.write_text(
            "# This is a comment\n"
            "\n"
            "Host srv\n"
            "    # Another comment\n"
            "    HostName 1.2.3.4\n"
            "    User root\n"
        )
        hosts = parse_ssh_config(ssh_config)
        assert len(hosts) == 1
        assert hosts[0].host == "1.2.3.4"

    def test_equals_syntax(self, tmp_path: Path):
        ssh_config = tmp_path / "config"
        ssh_config.write_text(
            "Host eqtest\n"
            "    HostName=192.168.1.1\n"
            "    Port=8022\n"
            "    User=testuser\n"
        )
        hosts = parse_ssh_config(ssh_config)
        assert len(hosts) == 1
        assert hosts[0].host == "192.168.1.1"
        assert hosts[0].port == 8022
        assert hosts[0].username == "testuser"

    def test_missing_file(self, tmp_path: Path):
        hosts = parse_ssh_config(tmp_path / "nonexistent")
        assert hosts == []

    def test_import_skips_existing(self, tmp_path: Path):
        ssh_config = tmp_path / "config"
        ssh_config.write_text(
            "Host existing\n"
            "    HostName 1.1.1.1\n"
            "\n"
            "Host new-one\n"
            "    HostName 2.2.2.2\n"
        )
        cfg = AppConfig(
            connections=[ConnectionConfig(name="existing", host="old.host")]
        )
        imported = cfg.import_ssh_config(ssh_config)
        assert len(imported) == 1
        assert imported[0].name == "new-one"
        # Original not overwritten
        assert cfg.find_connection("existing").host == "old.host"
