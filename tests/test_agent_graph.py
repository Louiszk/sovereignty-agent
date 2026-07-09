from langchain_core.messages import AIMessage, HumanMessage
from backend.agent import should_continue, AgentState


def test_should_continue_empty_messages():
    state: AgentState = {"messages": []}
    assert should_continue(state) == "end"


def test_should_continue_no_tool_calls():
    state: AgentState = {"messages": [HumanMessage(content="Hello"), AIMessage(content="Hi there!")]}
    assert should_continue(state) == "end"


def test_should_continue_with_tool_calls():
    msg_with_tools = AIMessage(
        content="",
        tool_calls=[{"name": "get_entity_score", "args": {"entity_id": "SVC-1"}, "id": "call_abc"}],
    )
    state: AgentState = {"messages": [HumanMessage(content="Score?"), msg_with_tools]}
    assert should_continue(state) == "continue"
