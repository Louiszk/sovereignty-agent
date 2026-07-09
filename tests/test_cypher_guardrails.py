import json
import pytest
from unittest.mock import patch
from backend.tools import execute_custom_cypher


@pytest.mark.parametrize(
    "dangerous_query",
    [
        "CREATE (n:Service {name: 'Malicious'})",
        "MATCH (n) DELETE n",
        "MATCH (n) SET n.name = 'Hacked'",
        "MATCH (n) REMOVE n.prop",
        "DROP INDEX chunk_index",
        "MERGE (n:Service {id: '123'})",
        "CALL apoc.periodic.iterate('MATCH (n) RETURN n', 'DELETE n', {})",
    ],
)
def test_execute_custom_cypher_blocks_write_queries(dangerous_query):
    result = execute_custom_cypher(dangerous_query)
    assert "FEHLER: Schreiboperationen sind aus Sicherheitsgründen in diesem Tool blockiert." in result


def test_execute_custom_cypher_success(mock_neo4j_driver):
    mock_data = [{"n": {"name": "SVC-Core-Banking"}}]

    with patch("backend.tools.driver", mock_neo4j_driver):
        # execute_read executes callback passed to session.execute_read
        mock_session = mock_neo4j_driver.session.return_value.__enter__.return_value
        mock_session.execute_read.return_value = mock_data

        result = execute_custom_cypher("MATCH (n:Service) RETURN n LIMIT 1")

        assert json.loads(result) == mock_data


def test_execute_custom_cypher_empty_result(mock_neo4j_driver):
    with patch("backend.tools.driver", mock_neo4j_driver):
        mock_session = mock_neo4j_driver.session.return_value.__enter__.return_value
        mock_session.execute_read.return_value = []

        result = execute_custom_cypher("MATCH (n:NonExistent) RETURN n")
        assert "keine Ergebnisse geliefert" in result


def test_execute_custom_cypher_token_limit_exceeded(mock_neo4j_driver):
    # Create large result over 80,000 tokens ("tokenword " * 1000 produces ~1000 tokens per row)
    large_text = "tokenword " * 1000
    mock_data = [{"content": large_text} for _ in range(150)]

    with patch("backend.tools.driver", mock_neo4j_driver):
        mock_session = mock_neo4j_driver.session.return_value.__enter__.return_value
        mock_session.execute_read.return_value = mock_data

        result = execute_custom_cypher("MATCH (n) RETURN n")
        assert "FEHLER: Das Ergebnis ist zu groß" in result
        assert "Token-Limit (80k Tokens) wurde überschritten" in result
