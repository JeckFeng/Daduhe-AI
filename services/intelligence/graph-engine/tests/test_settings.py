"""Test pydantic-settings configuration with GRAPH_ prefix."""

from src.settings import Settings


class TestSettingsDefaults:
    """Verify default values match the project infrastructure."""

    def test_default_memgraph_uri(self):
        s = Settings()
        assert s.memgraph_uri == "bolt://localhost:17687"

    def test_default_memgraph_credentials_are_empty(self):
        s = Settings()
        assert s.memgraph_username == ""
        assert s.memgraph_password == ""

    def test_default_memgraph_database(self):
        s = Settings()
        assert s.memgraph_database == "memgraph"

    def test_default_pg_host(self):
        s = Settings()
        assert s.pg_host == "localhost"

    def test_default_pg_port_is_ssh_tunnel(self):
        s = Settings()
        assert s.pg_port == 5434

    def test_default_pg_user(self):
        s = Settings()
        assert s.pg_user == "daduhe"

    def test_default_pg_password_is_empty(self, monkeypatch):
        monkeypatch.delenv("GRAPH_PG_PASSWORD", raising=False)
        s = Settings()
        assert s.pg_password == ""

    def test_default_pg_database(self):
        s = Settings()
        assert s.pg_database == "mydatabase"

    def test_default_llm_gateway_url(self):
        s = Settings()
        assert s.llm_gateway_url == "http://localhost:8004"

    def test_default_gleaning_rounds(self):
        s = Settings()
        assert s.entity_extract_max_gleaning == 1

    def test_default_max_source_ids(self):
        s = Settings()
        assert s.max_source_ids_per_entity == 10

    def test_default_prompt_profile_path(self):
        s = Settings()
        assert s.prompt_profile_path == "entity_type/water_conservancy.yaml"


class TestSettingsFromEnv:
    """Verify environment variable overrides work correctly."""

    def test_graph_prefix_overrides_default(self, monkeypatch):
        monkeypatch.setenv("GRAPH_MEMGRAPH_URI", "bolt://custom:12345")
        monkeypatch.setenv("GRAPH_PG_HOST", "pg.example.com")
        s = Settings()
        assert s.memgraph_uri == "bolt://custom:12345"
        assert s.pg_host == "pg.example.com"

    def test_gleaning_can_be_disabled(self, monkeypatch):
        monkeypatch.setenv("GRAPH_ENTITY_EXTRACT_MAX_GLEANING", "0")
        s = Settings()
        assert s.entity_extract_max_gleaning == 0

    def test_pg_config_override(self, monkeypatch):
        monkeypatch.setenv("GRAPH_PG_PORT", "5432")
        monkeypatch.setenv("GRAPH_PG_DATABASE", "testdb")
        s = Settings()
        assert s.pg_port == 5432
        assert s.pg_database == "testdb"
