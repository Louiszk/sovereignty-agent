from backend.tools import (
    calculate_sovereignty_score,
    get_chunk_content,
    get_entity_description,
    execute_custom_cypher,
    sparse_search,
)
from backend.utils import get_dynamic_schema, execute_tool_calls
from backend.prompts import get_system_prompt
from typing import Annotated, TypedDict
from langchain_openai import ChatOpenAI
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig
from backend.config import AGENT_RECURSION_LIMIT
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.checkpoint.memory import MemorySaver
import tiktoken
import logging
import concurrent.futures
from langgraph.errors import GraphRecursionError

logger = logging.getLogger(__name__)

encoder = tiktoken.get_encoding("o200k_base")


# Define the tool
@tool
def get_entity_score(entity_id: str) -> str:
    """
    Nutze dieses Tool IMMER, wenn der Nutzer nach dem Score, dem Status oder
    der Bewertung der digitalen Souveränität einer bestimmten Entity fragt.
    """
    return calculate_sovereignty_score(entity_id)


@tool
def read_evidence_chunk(chunk_id: str) -> str:
    """
    Nutze dieses Tool, um die genauen Belege und Vertragstexte zu lesen,
    die z.B als ChunkID im Score-Report aufgeführt sind.
    Das hilft dir, dem Nutzer genaue Erklärungen für Punktabzüge zu geben.
    """
    return get_chunk_content(chunk_id)


@tool
def read_entity_description(entity_id: str) -> str:
    """
    Nutze dieses Tool, um herauszufinden, was ein bestimmter Service oder Provider (z.B. SVC-1) überhaupt macht.
    Es liefert dir eine detaillierte System- oder Providerbeschreibung (TextChunk) für die gegebene ID.
    """
    return get_entity_description(entity_id)


@tool
def execute_cypher_query(query: str) -> str:
    """
    Führt eine READ-ONLY Cypher-Query auf der Neo4j-Datenbank aus.
    Nutze dieses Tool, um beliebige Fragen des Nutzers über die Architektur, Provider oder Daten zu beantworten,
    die über den reinen Souveränitäts-Score hinausgehen.
    Nutze bei unklaren Ergebnismengen immer ein LIMIT (z.B. LIMIT 10), um das Kontext-Fenster nicht zu sprengen!
    """
    return execute_custom_cypher(query)


@tool
def search_chunks(keywords: list[str]) -> str:
    """
    Nutze dieses Tool, um in unstrukturierten Texten (Verträgen, Policys, Architektur-Entscheidungen) nach Stichworten zu suchen.
    Beispiel-Keywords: ['Kündigungsfrist', 'Sanktionen', 'Datenresidenz', 'Migration'] oder auch englische Begriffe.
    """
    return sparse_search(keywords)


tools = [get_entity_score, read_evidence_chunk, read_entity_description, execute_cypher_query, search_chunks]
tool_map = {tool.name: tool for tool in tools}

# Initialize LLM and bind tools
llm = ChatOpenAI(model="gpt-5.4-mini", temperature=0)
llm_with_tools = llm.bind_tools(tools)


# Define the state for the graph
class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]


# Node: Call the LLM
def call_model(state: AgentState):
    messages = state.get("messages", [])
    response = llm_with_tools.invoke(messages)
    return {"messages": [response]}


# Node: Execute the tools
def call_tools(state: AgentState):
    messages = state.get("messages", [])
    last_message = messages[-1] if messages else None

    if not last_message:
        return {"messages": []}

    tool_responses = execute_tool_calls(last_message, tool_map)
    return {"messages": tool_responses}


# Conditional edge: Decide whether to continue or end
def should_continue(state: AgentState) -> str:
    messages = state.get("messages", [])
    if not messages:
        return "end"
    last_message = messages[-1]

    if getattr(last_message, "tool_calls", None):
        return "continue"
    return "end"


# Build the graph
workflow = StateGraph(AgentState)

workflow.add_node("agent", call_model)
workflow.add_node("tools", call_tools)

workflow.add_edge(START, "agent")
workflow.add_edge("tools", "agent")

workflow.add_conditional_edges("agent", should_continue, {"continue": "tools", "end": END})

# Initialize MemorySaver
memory = MemorySaver()
agent_executor = workflow.compile(checkpointer=memory)


def chat_with_agent(user_message: str, session_id: str = "default") -> str:
    logger.info(f"Starting agent workflow for session '{session_id}'")

    sys_msg = SystemMessage(
        content=get_system_prompt(get_dynamic_schema()),
        id="system_prompt",
    )

    config = RunnableConfig(configurable={"thread_id": session_id}, recursion_limit=AGENT_RECURSION_LIMIT)

    # Token count check using o200k_base before invoking
    state = agent_executor.get_state(config)
    history = state.values.get("messages", [])

    estimated_tokens = sum(len(encoder.encode(str(m.content))) for m in history if m.content)

    if estimated_tokens > 400000:
        logger.warning(f"Token limit exceeded for session '{session_id}' ({estimated_tokens} tokens)")
        # TODO: In the future, this could also be a summarizer to compress the context instead of hard-stopping.
        return "Der Kontext ist zu lang geworden (>400.000 Tokens). Bitte lade die Seite neu, um einen neuen Chat zu starten."

    inputs: AgentState = {"messages": [sys_msg, HumanMessage(content=user_message)]}

    logger.info("Invoking LangGraph executor...")
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(lambda: agent_executor.invoke(inputs, config=config))
            final_state = future.result(timeout=120.0)
        logger.info("LangGraph execution completed.")
    except concurrent.futures.TimeoutError:
        logger.error(f"Agent execution timed out after 120s for session '{session_id}'")
        return "FEHLER: Der Agent hat zu lange für eine Antwort gebraucht (Timeout nach 120 Sekunden). Bitte versuche es noch einmal."
    except GraphRecursionError:
        logger.error(f"Agent hit recursion limit ({AGENT_RECURSION_LIMIT}) for session '{session_id}'")
        return "FEHLER: Der Agent hat das interne Iterations-Limit erreicht. Bitte teile deine Anfrage in kleinere, spezifischere Fragen auf."
    except Exception as e:
        logger.error(f"Agent execution error: {e}", exc_info=True)
        return "FEHLER: Bei der Verarbeitung deiner Anfrage ist ein unerwartetes Problem aufgetreten."

    # Safely extract the last message content
    messages = final_state.get("messages", [])
    if messages:
        return str(messages[-1].content)
    else:
        logger.error(f"No messages found in final state for session '{session_id}'")
        return "FEHLER: Der Agent hat eine leere Antwort zurückgegeben."
