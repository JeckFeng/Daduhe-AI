"""Test PostgreSQL table creation (requires DB password via env)."""

import psycopg2
import pytest

pytestmark = pytest.mark.integration


@pytest.fixture
def pg_conn():
    """Connect to PostgreSQL using SSH tunnel."""
    try:
        conn = psycopg2.connect(
            host="localhost",
            port=5434,
            user="daduhe",
            password="gis31415",
            dbname="mydatabase",
            connect_timeout=5,
        )
        yield conn
        conn.close()
    except Exception:
        pytest.skip("PostgreSQL not reachable (SSH tunnel down?)")


class TestGraphEngineTables:
    """Verify graph_engine schema and tables exist."""

    def test_graph_engine_schema_exists(self, pg_conn):
        cur = pg_conn.cursor()
        cur.execute(
            "SELECT schema_name FROM information_schema.schemata WHERE schema_name='graph_engine'"
        )
        assert cur.fetchone() is not None
        cur.close()

    def test_extraction_tasks_table(self, pg_conn):
        cur = pg_conn.cursor()
        cur.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_schema='graph_engine' AND table_name='extraction_tasks'
            ORDER BY ordinal_position
        """)
        cols = [r[0] for r in cur.fetchall()]
        assert "task_id" in cols
        assert "doc_id" in cols
        assert "status" in cols
        assert "progress" in cols
        assert "result" in cols
        assert "error_message" in cols
        cur.close()

    def test_llm_cache_table(self, pg_conn):
        cur = pg_conn.cursor()
        cur.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_schema='graph_engine' AND table_name='llm_cache'
            ORDER BY ordinal_position
        """)
        cols = [r[0] for r in cur.fetchall()]
        assert "cache_key" in cols
        assert "model" in cols
        assert "system_prompt" in cols
        assert "user_prompt" in cols
        assert "response" in cols
        cur.close()

    def test_tables_are_idempotent(self, pg_conn):
        """CREATE IF NOT EXISTS should not error on re-run."""
        cur = pg_conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS graph_engine.extraction_tasks (
                task_id VARCHAR(64) PRIMARY KEY,
                doc_id VARCHAR(64) NOT NULL,
                status VARCHAR(20) NOT NULL DEFAULT 'pending',
                progress JSONB DEFAULT '{}',
                result JSONB DEFAULT '{}',
                error_message TEXT,
                created_at TIMESTAMPTZ DEFAULT now(),
                updated_at TIMESTAMPTZ DEFAULT now(),
                completed_at TIMESTAMPTZ
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS graph_engine.llm_cache (
                cache_key VARCHAR(64) PRIMARY KEY,
                model VARCHAR(128) NOT NULL,
                system_prompt TEXT NOT NULL,
                user_prompt TEXT NOT NULL,
                response JSONB NOT NULL,
                created_at TIMESTAMPTZ DEFAULT now()
            )
        """)
        pg_conn.commit()
        cur.close()
