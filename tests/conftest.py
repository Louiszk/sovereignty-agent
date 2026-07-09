import os
import pytest

# Ensure required environment variables exist for module load (e.g. ChatOpenAI / Neo4j config)
os.environ.setdefault("OPENAI_API_KEY", "sk-mock-key-for-unit-testing-0000000000000")
os.environ.setdefault("NEO4J_USER", "neo4j")
os.environ.setdefault("NEO4J_PASSWORD", "password")

from unittest.mock import MagicMock
from fastapi.testclient import TestClient
from backend.main import app


@pytest.fixture
def mock_neo4j_session():
    """Returns a MagicMock simulating a Neo4j Session inside a context manager."""
    session = MagicMock()
    return session


@pytest.fixture
def mock_neo4j_driver(mock_neo4j_session):
    """Returns a MagicMock simulating a Neo4j Driver where session() works as a context manager."""
    driver = MagicMock()
    # Support 'with driver.session() as session:'
    session_cm = MagicMock()
    session_cm.__enter__.return_value = mock_neo4j_session
    session_cm.__exit__.return_value = None
    driver.session.return_value = session_cm
    return driver


@pytest.fixture
def api_client():
    """Returns a FastAPI TestClient for the application."""
    with TestClient(app) as client:
        yield client
