from unittest.mock import patch
from langchain_core.messages import AIMessage
from langchain_core.tools import tool
from backend.utils import execute_tool_calls, get_chunk_data


@tool
def sample_tool(text: str) -> str:
    """A sample tool for testing."""
    return f"Processed: {text}"


@tool
def failing_tool(text: str) -> str:
    """A tool that raises an exception."""
    raise ValueError("Intentional failure")


def test_execute_tool_calls_success():
    msg = AIMessage(
        content="",
        tool_calls=[{"name": "sample_tool", "args": {"text": "hello"}, "id": "call_123"}],
    )
    tools = {"sample_tool": sample_tool}

    messages = execute_tool_calls(msg, tools)
    assert len(messages) == 1
    assert messages[0].content == "Processed: hello"
    assert messages[0].tool_call_id == "call_123"
    assert messages[0].name == "sample_tool"


def test_execute_tool_calls_not_found():
    msg = AIMessage(
        content="",
        tool_calls=[{"name": "unknown_tool", "args": {}, "id": "call_999"}],
    )
    tools = {}

    messages = execute_tool_calls(msg, tools)
    assert len(messages) == 1
    assert "not found" in messages[0].content
    assert messages[0].tool_call_id == "call_999"


def test_execute_tool_calls_exception():
    msg = AIMessage(
        content="",
        tool_calls=[{"name": "failing_tool", "args": {"text": "boom"}, "id": "call_err"}],
    )
    tools = {"failing_tool": failing_tool}

    messages = execute_tool_calls(msg, tools)
    assert len(messages) == 1
    assert "Error executing tool failing_tool" in messages[0].content


def test_get_chunk_data_adds_prefix_and_returns_data(mock_neo4j_driver, mock_neo4j_session):
    mock_neo4j_session.run.return_value.single.return_value = {
        "title": "Kündigungsklausel",
        "type": "Contract",
        "source_file": "contract.pdf",
        "content": "Frist 3 Monate",
    }

    with patch("backend.utils.driver", mock_neo4j_driver):
        result = get_chunk_data("001")
        assert result["title"] == "Kündigungsklausel"
        assert result["type"] == "Contract"
        assert result["content"] == "Frist 3 Monate"
        # Check that CHK- prefix was prepended
        mock_neo4j_session.run.assert_called_once()
        args, kwargs = mock_neo4j_session.run.call_args
        assert kwargs["chunk_id"] == "CHK-001"
