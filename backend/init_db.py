import os
import json
from typing import cast, LiteralString
from neo4j import GraphDatabase
from backend.config import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD

# Path to Graph Data
DATA_PATH = os.getenv("DATA_PATH", "/app/data/graph_data.json")


def init_db():
    local_path = os.path.join(os.path.dirname(__file__), "..", "data", "graph_data.json")

    if os.path.exists(DATA_PATH):
        file_to_load = DATA_PATH
    elif os.path.exists(local_path):
        file_to_load = local_path
    else:
        print(f"Error: JSON file not found at {DATA_PATH} or {local_path}")
        return

    print(f"Loading JSON from {file_to_load}")
    try:
        with open(file_to_load, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError:
        print("Error: Invalid JSON format.")
        return

    print("Connecting to Neo4j...")
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

    nodes = data.get("nodes", [])
    edges = data.get("edges", [])

    with driver.session() as session:
        # Reset database
        print("Clearing existing database...")
        session.run("MATCH (n) DETACH DELETE n")

        # Import nodes
        print(f"Inserting {len(nodes)} nodes...")
        for node in nodes:
            node_id = node.get("id")
            # Fallback label 'Entity', if none is specified
            label = node.get("label", "Entity")
            props = node.get("properties", {})
            props["id"] = node_id

            query = cast(LiteralString, f"CREATE (n:{label} $props)")
            session.run(query, props=props)

        # Import edges
        print(f"Inserting {len(edges)} edges...")
        for edge in edges:
            source = edge.get("source")
            target = edge.get("target")
            rel_type = edge.get("label", "RELATED_TO")
            props = edge.get("properties", {})

            query = cast(
                LiteralString,
                f"""
            MATCH (a {{id: $source}})
            MATCH (b {{id: $target}})
            CREATE (a)-[r:{rel_type} $props]->(b)
            """,
            )
            session.run(query, source=source, target=target, props=props)

        # Create Full-Text Index for Sparse Search
        print("Creating Full-Text Index for TextChunks...")
        try:
            session.run("""
            CREATE FULLTEXT INDEX chunk_index IF NOT EXISTS 
            FOR (n:TextChunk) ON EACH [n.title, n.content]
            """)
        except Exception as e:
            print(f"Warning: Index creation failed (might already exist): {e}")

    driver.close()
    print("Graph initialized successfully!")


if __name__ == "__main__":
    init_db()
