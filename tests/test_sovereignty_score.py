from unittest.mock import patch, MagicMock
from backend.tools import calculate_sovereignty_score


def test_calculate_sovereignty_score_entity_not_found(mock_neo4j_driver, mock_neo4j_session):
    mock_neo4j_session.run.return_value.single.return_value = None

    with patch("backend.tools.driver", mock_neo4j_driver):
        result = calculate_sovereignty_score("INVALID-ID")
        assert result == "Entity mit ID INVALID-ID nicht gefunden."


def test_calculate_sovereignty_score_no_dependencies(mock_neo4j_driver, mock_neo4j_session):
    # First query (paths) returns None, fallback check query returns entity name
    call_count = 0

    def fake_run(query, **kwargs):
        nonlocal call_count
        call_count += 1
        mock_res = MagicMock()
        if call_count == 1:
            mock_res.single.return_value = None
        else:
            mock_res.single.return_value = {"name": "Core Banking API"}
        return mock_res

    mock_neo4j_session.run.side_effect = fake_run

    with patch("backend.tools.driver", mock_neo4j_driver):
        result = calculate_sovereignty_score("SVC-CORE")
        assert "Souveränitäts-Score für Core Banking API: 100.0/100" in result
        assert "Keine Abhängigkeiten gefunden." in result


def test_calculate_sovereignty_score_with_risks(mock_neo4j_driver, mock_neo4j_session):
    # Mock entity and relationships with USA residency, High lock-in, long contract
    mock_record = {
        "entity_name": "Payment Service",
        "distinct_rels": [
            {
                "rel": {
                    "data_residency": "USA",
                    "jurisdiction": "USA",
                    "lock_in_level": "High",
                    "contract_duration_months": 36,
                    "dependency_mode": "required",
                    "provenance_chunk_id": "CHK-001",
                },
                "target_id": "PRV-AWS",
                "target_name": "AWS Cloud",
                "target_is_internal": False,
                "depth": 1,
                "source_id": "SVC-PAY",
                "source_name": "Payment Service",
                "source_criticality": "High",
            }
        ],
    }

    mock_neo4j_session.run.return_value.single.return_value = mock_record

    with patch("backend.tools.driver", mock_neo4j_driver):
        report = calculate_sovereignty_score("SVC-PAY")

        assert "Souveränitäts-Score für Payment Service:" in report
        # Verify score is below 100 due to penalties across dimensions
        assert "100.0/100" not in report
        assert "Kritische Risiken:" in report
        assert "Datenresidenz USA bei 'AWS Cloud (Externer Provider/SaaS)'" in report
        assert "[[CHK-001]]" in report
