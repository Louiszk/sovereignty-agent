from backend.config import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD

import os
import json
from typing import cast, LiteralString
from neo4j import GraphDatabase
from langchain_openai import OpenAIEmbeddings

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

        # Create Vector Index for Dense Search
        print("Creating Vector Index for TextChunks...")
        try:
            session.run("""
            CREATE VECTOR INDEX vector_index IF NOT EXISTS 
            FOR (n:TextChunk) ON (n.embedding) 
            OPTIONS {indexConfig: {
                `vector.dimensions`: 1536,
                `vector.similarity_function`: 'cosine'
            }}
            """)
        except Exception as e:
            print(f"Warning: Vector Index creation failed: {e}")

        # Generate embeddings for TextChunks
        try:
            embeddings = OpenAIEmbeddings(model="text-embedding-3-small")

            chunks = session.run(
                "MATCH (n:TextChunk) WHERE n.embedding IS NULL RETURN id(n) AS node_id, n.content AS content, n.title AS title"
            ).data()
            if chunks:
                print(f"Generating embeddings for {len(chunks)} TextChunks...")
                for chunk in chunks:
                    text_to_embed = f"{chunk.get('title', '')}\n{chunk.get('content', '')}"
                    emb = embeddings.embed_query(text_to_embed)
                    session.run(
                        "MATCH (n:TextChunk) WHERE id(n) = $node_id SET n.embedding = $emb",
                        node_id=chunk["node_id"],
                        emb=emb,
                    )
                print("Finished generating embeddings.")
            else:
                print("No chunks require embeddings.")
        except Exception as e:
            print(f"Warning: Could not generate embeddings: {e}")

    driver.close()
    print("Graph initialized successfully!")


if __name__ == "__main__":
    init_db()
