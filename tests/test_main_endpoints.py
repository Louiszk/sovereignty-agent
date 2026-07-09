from unittest.mock import patch


def test_chat_endpoint_success(api_client):
    with patch("backend.main.chat_with_agent") as mock_chat:
        mock_chat.return_value = "Der Souveränitäts-Score beträgt 85.0/100."

        response = api_client.post(
            "/api/chat",
            json={"message": "Wie ist der Score für SVC-1?", "session_id": "test_sess"},
        )

        assert response.status_code == 200
        assert response.json() == {"reply": "Der Souveränitäts-Score beträgt 85.0/100."}
        mock_chat.assert_called_once_with("Wie ist der Score für SVC-1?", "test_sess")


def test_chat_endpoint_error_handling(api_client):
    with patch("backend.main.chat_with_agent") as mock_chat:
        mock_chat.side_effect = RuntimeError("OpenAI connection failed")

        response = api_client.post(
            "/api/chat",
            json={"message": "Hallo", "session_id": "test_sess"},
        )

        assert response.status_code == 200
        assert "Ein interner Fehler ist aufgetreten" in response.json()["reply"]


def test_get_chunk_endpoint_success(api_client):
    mock_chunk = {
        "title": "AWS DPA",
        "type": "Contract",
        "source_file": "aws.pdf",
        "content": "Data transfer clause...",
    }
    with patch("backend.main.get_chunk_data", return_value=mock_chunk):
        response = api_client.get("/api/chunk/CHK-001")

        assert response.status_code == 200
        assert response.json() == mock_chunk


def test_get_chunk_endpoint_not_found(api_client):
    with patch("backend.main.get_chunk_data", return_value={}):
        response = api_client.get("/api/chunk/CHK-999")

        assert response.status_code == 200
        assert response.json() == {"error": "Chunk nicht gefunden."}
