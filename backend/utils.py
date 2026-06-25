import logging
from neo4j import GraphDatabase
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
