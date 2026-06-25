import logging
from typing import List, Dict
from neo4j import GraphDatabase
from langchain_core.tools import BaseTool
from langchain_core.messages import ToolMessage, BaseMessage
from backend.config import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD

logger = logging.getLogger(__name__)
driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))


def get_dynamic_schema() -> str:
    """
    Extracts the graph schema (Labels, Relationship Types, and Properties) directly from Neo4j.
    """
    try:
        with driver.session() as session:
            node_props_result = session.run("CALL db.schema.nodeTypeProperties()")
            node_schema = {}
            for record in node_props_result:
                label = record["nodeType"].replace(":`", "").replace("`", "")
                prop = record["propertyName"]
                if label not in node_schema:
                    node_schema[label] = []
                if prop:
                    node_schema[label].append(prop)

            rel_props_result = session.run("CALL db.schema.relTypeProperties()")
            rel_schema = {}
            for record in rel_props_result:
                rel_type = record["relType"].replace(":`", "").replace("`", "")
                prop = record["propertyName"]
                if rel_type not in rel_schema:
                    rel_schema[rel_type] = []
                if prop:
                    rel_schema[rel_type].append(prop)

        schema_str = "- Nodes:\n"
        for label, props in node_schema.items():
            schema_str += f"  - :{label} (Properties: {', '.join(props) if props else 'None'})\n"

        schema_str += "- Relationships:\n"
        for rel_type, props in rel_schema.items():
            schema_str += f"  - -[:{rel_type}]-> (Properties: {', '.join(props) if props else 'None'})\n"

        return schema_str
    except Exception as e:
        logger.error(f"Could not load dynamic schema: {e}")
        return "- Schema konnte nicht geladen werden."


def execute_tool_calls(response: BaseMessage, available_tools: Dict[str, BaseTool]) -> List[ToolMessage]:
    """Execute available tool calls from the response robustly."""
    tool_messages = []

    # Handle invalid tool calls if present
    for invalid_call in getattr(response, "invalid_tool_calls", []) or []:
        if isinstance(invalid_call, dict):
            err = invalid_call.get("error")
            cid = invalid_call.get("id")
            name = invalid_call.get("name")
        else:
            err = getattr(invalid_call, "error", None)
            cid = getattr(invalid_call, "id", None)
            name = getattr(invalid_call, "name", None)

        content = f"Failed to parse tool call. Error: {err}"
        tool_messages.append(ToolMessage(content=content, tool_call_id=cid, name=name))

    tool_calls = getattr(response, "tool_calls", []) or []
    if not tool_calls:
        return tool_messages

    for tool_call in tool_calls:
        if not tool_call:
            continue

        if isinstance(tool_call, dict):
            tool_name = tool_call.get("name")
            tool_args = tool_call.get("args", {}) or {}
            tool_id = tool_call.get("id")
        else:
            tool_name = getattr(tool_call, "name", None)
            tool_args = getattr(tool_call, "args", {}) or {}
            tool_id = getattr(tool_call, "id", None)

        if not tool_name:
            tool_messages.append(
                ToolMessage(
                    content="Malformed tool call: missing name",
                    tool_call_id=tool_id,
                    name=None,
                )
            )
            continue

        if tool_name in available_tools:
            try:
                result = available_tools[tool_name].invoke(tool_args)
                content = str(result) if result is not None else f"Tool {tool_name} executed successfully."
                tool_messages.append(ToolMessage(content=content, tool_call_id=tool_id, name=tool_name))
            except Exception as e:
                error_message = f"Error executing tool {tool_name}: {repr(e)}"
                tool_messages.append(ToolMessage(content=error_message, tool_call_id=tool_id, name=tool_name))
        else:
            tool_messages.append(
                ToolMessage(
                    content=f"Tool {tool_name} not found.",
                    tool_call_id=tool_id,
                    name=tool_name,
                )
            )

    return tool_messages


def get_chunk_data(chunk_id: str) -> dict:
    """
    Retrieves the raw text content and type of a TextChunk by its ID as a dictionary.
    """
    from typing import cast, LiteralString

    if not chunk_id.startswith("CHK-"):
        chunk_id = f"CHK-{chunk_id}"

    logger.info(f"Retrieving chunk data for chunk_id: {chunk_id}")
    query = cast(
        LiteralString,
        """
        MATCH (c:TextChunk {id: $chunk_id})
        RETURN c.type AS type, c.title AS title, c.content AS content, c.source_file AS source_file
        """,
    )
    with driver.session() as session:
        result = session.run(query, chunk_id=chunk_id).single()

    if not result:
        return {}

    return {
        "title": result.get("title", "Kein Titel"),
        "type": result["type"],
        "source_file": result.get("source_file"),
        "content": result["content"],
    }
