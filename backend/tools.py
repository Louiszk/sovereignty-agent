from typing import cast, LiteralString
import json
import neo4j.exceptions
import tiktoken
import concurrent.futures
from neo4j import GraphDatabase
from backend.config import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, METRIC_CONFIGS
import logging

logger = logging.getLogger(__name__)
encoder = tiktoken.get_encoding("o200k_base")

driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))


def calculate_sovereignty_score(entity_id: str) -> str:
    """
    Calculates the digital sovereignty score for an entity.
    Collects all edges in the dependency tree and cumulates the
    risk metadata stored there into a deterministic score.
    """
    logger.info(f"Calculating sovereignty score for entity_id: {entity_id}")
    # Cypher: Find the entity, traverse all dependencies and collect all UNIQUE edges
    query = cast(
        LiteralString,
        """
        MATCH (s {id: $entity_id})
        WHERE NOT 'TextChunk' IN labels(s)
        OPTIONAL MATCH path = (s)-[:DEPENDS_ON|RUNS_ON*1..]->()
        UNWIND relationships(path) AS rel
        WITH s.name AS entity_name, rel, startNode(rel) AS source, endNode(rel) AS target
        RETURN entity_name, collect(DISTINCT {
            rel: rel, 
            source_id: source.id, 
            source_name: source.name,
            source_labels: labels(source),
            target_id: target.id, 
            target_name: target.name,
            target_labels: labels(target)
        }) AS distinct_rels
        """,
    )

    with driver.session() as session:
        result = session.run(query, entity_id=entity_id).single()

    # Fallback if the entity exists but has no outgoing edges
    if not result:
        # Check if the entity exists at all
        check_query = cast(LiteralString, "MATCH (s {id: $entity_id}) WHERE NOT s:TextChunk RETURN s.name AS name")
        with driver.session() as session:
            check = session.run(check_query, entity_id=entity_id).single()
        if check:
            return f"Souveränitäts-Score für {check['name']}: 100/100\nKeine Abhängigkeiten gefunden."
        return f"Entity mit ID {entity_id} nicht gefunden."

    entity_name = result["entity_name"]
    rels = result["distinct_rels"]

    # Base score
    score = 100
    penalties = []

    # Track the worst penalty found per property to avoid double counting
    worst_penalties = {
        config["property"]: {"penalty": 0, "msg": "", "chunk_id": None, "source_info": None, "target_info": None}
        for config in METRIC_CONFIGS
    }

    # Scan all edges in the subgraph to find the worst-case risks
    for item in rels:
        if item is None or item.get("rel") is None:
            continue

        rel = item["rel"]
        chunk_id = rel.get("provenance_chunk_id")

        for config in METRIC_CONFIGS:
            prop = config["property"]
            val = rel.get(prop)
            if val is None:
                continue

            # Evaluate rules (ordered by severity)
            for rule in config["rules"]:
                matched = False
                if config["is_numeric"] and isinstance(val, (int, float)):
                    if val >= rule["min_val"]:
                        matched = True
                elif not config["is_numeric"]:
                    if val == rule["match"]:
                        matched = True

                if matched:
                    if rule["penalty"] > worst_penalties[prop]["penalty"]:
                        msg = rule["msg"].replace("{val}", str(val))
                        source_lbl = item["source_labels"][0] if item["source_labels"] else "Unknown"
                        target_lbl = item["target_labels"][0] if item["target_labels"] else "Unknown"

                        worst_penalties[prop] = {
                            "penalty": rule["penalty"],
                            "msg": msg,
                            "chunk_id": chunk_id,
                            "source_info": f"{source_lbl} '{item.get('source_name', 'Unknown')}' ({item.get('source_id', 'Unknown')})",
                            "target_info": f"{target_lbl} '{item.get('target_name', 'Unknown')}' ({item.get('target_id', 'Unknown')})",
                        }
                    break

    # Apply all collected worst-case penalties
    for prop, data in worst_penalties.items():
        if data["penalty"] > 0:
            score -= data["penalty"]
            ref = f" (Beleg: {data['chunk_id']})" if data["chunk_id"] else ""
            path_info = f" [Gefunden zwischen {data['source_info']} und {data['target_info']}]"
            penalties.append(f"-{data['penalty']} Pkt: {data['msg']}{path_info}{ref}")

    # Normalize score (not below 0)
    score = max(0, score)

    # Format report
    report = f"Souveränitäts-Score für {entity_name}: {score}/100\n"
    if penalties:
        report += "Identifizierte Risikofaktoren auf den Kanten:\n" + "\n".join(penalties)
    else:
        report += "Keine kritischen Souveränitätsrisiken in den Abhängigkeiten identifiziert."

    logger.info(f"Score for {entity_id} calculated as {score} with {len(penalties)} penalties.")
    return report


def get_chunk_content(chunk_id: str) -> str:
    """
    Retrieves the raw text content and type of a TextChunk by its ID.
    """
    logger.info(f"Retrieving chunk content for chunk_id: {chunk_id}")
    query = cast(
        LiteralString,
        """
        MATCH (c:TextChunk {id: $chunk_id})
        RETURN c.type AS type, c.title AS title, c.content AS content
        """,
    )
    with driver.session() as session:
        result = session.run(query, chunk_id=chunk_id).single()

    if not result:
        return f"TextChunk mit ID {chunk_id} nicht gefunden."

    return f"Titel: {result.get('title', 'Kein Titel')}\nTyp: {result['type']}\nInhalt: {result['content']}"


def get_entity_description(entity_id: str) -> str:
    """
    Retrieves the description TextChunk for a given entity ID.
    """
    logger.info(f"Retrieving entity description for entity_id: {entity_id}")
    query = cast(
        LiteralString,
        """
        MATCH (e {id: $entity_id})-[:DESCRIBED_BY]->(c:TextChunk)
        RETURN c.id AS id, c.title AS title, c.content AS content
        """,
    )
    with driver.session() as session:
        result = session.run(query, entity_id=entity_id).single()

    if not result:
        return f"Keine Beschreibung (TextChunk) für Entity ID {entity_id} gefunden."

    return f"Chunk ID: {result['id']}\nTitel: {result.get('title', 'Kein Titel')}\nBeschreibung: {result['content']}"


def execute_custom_cypher(query: str) -> str:
    """
    Executes a custom read-only Cypher query against the Neo4j database.
    Guardrails: 20s timeout, read-only enforcement, max 80,000 tokens output.
    """
    logger.info(f"Executing custom Cypher: {query}")

    # Simple static check for obvious write commands
    upper_query = query.upper()
    if any(
        forbidden in upper_query for forbidden in ["CREATE", "SET", "DELETE", "REMOVE", "DROP", "MERGE", "CALL apoc"]
    ):
        return "FEHLER: Schreiboperationen sind aus Sicherheitsgründen in diesem Tool blockiert."

    def _read_tx(tx):
        result = tx.run(query)
        data = []
        for i, record in enumerate(result):
            if i >= 1000:
                data.append(
                    {
                        "warning": "Ergebnis auf 1000 Zeilen limitiert. Bitte verwende LIMIT oder Aggregationen in der Query."
                    }
                )
                break
            data.append(record.data())
        return data

    def _run_query():
        with driver.session() as session:
            return session.execute_read(_read_tx)

    try:
        # Strict Python-level timeout to guarantee the agent never hangs
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_run_query)
            results = future.result(timeout=20.0)

        json_output = json.dumps(results, ensure_ascii=False, default=str)

        # Check Token Limit using tiktoken (max 80,000 tokens)
        token_count = len(encoder.encode(json_output))
        if token_count > 80000:
            return f"FEHLER: Das Ergebnis ist zu groß ({token_count} Tokens). Das Token-Limit (80k Tokens) wurde überschritten. Bitte aggregiere die Daten (z.B. mit count()) oder setze ein striktes LIMIT."

        return json_output

    except concurrent.futures.TimeoutError:
        logger.error(f"Cypher Query Timeout: {query}")
        return "FEHLER: Die Ausführung der Cypher-Query hat zu lange gedauert (> 20 Sekunden) und wurde abgebrochen. Wahrscheinlich war die Query zu komplex."
    except neo4j.exceptions.ClientError as e:
        logger.error(f"Cypher Syntax/Client Error: {e}")
        return f"FEHLER in der Cypher-Query: {e}"
    except Exception as e:
        logger.error(f"Execution Error: {e}")
        return f"FEHLER bei der Ausführung: {e}"


def sparse_search(keywords: list[str]) -> str:
    """
    Executes a full-text search (Sparse Search / BM25) across all documents and contracts.
    Returns the most relevant TextChunks based on the provided keywords.
    """
    if not keywords:
        return "FEHLER: Keine Keywords angegeben."

    search_query = " OR ".join(f'"{kw}"' for kw in keywords)
    logger.info(f"Executing sparse search for: {search_query}")

    query = cast(
        LiteralString,
        """
        CALL db.index.fulltext.queryNodes("chunk_index", $search_query) YIELD node, score
        RETURN node.id AS id, node.title AS title, node.type AS type, node.content AS content, score
        ORDER BY score DESC
        LIMIT 3
        """,
    )

    with driver.session() as session:
        result = session.run(query, search_query=search_query).data()

    if not result:
        return f"Keine relevanten Dokumente für die Suchbegriffe {keywords} gefunden."

    formatted_results = []
    for r in result:
        # Finde auch heraus, an welchen Services/Providern dieses Dokument hängt
        connected_query = cast(
            LiteralString,
            "MATCH (c:TextChunk {id: $chunk_id})-[:RELATES_TO|DESCRIBED_BY]-(related) RETURN collect(related.name) AS related_entities",
        )
        with driver.session() as session:
            conn_res = session.run(connected_query, chunk_id=r["id"]).single()

        related = conn_res["related_entities"] if conn_res else []
        related_str = f"Verknüpft mit: {', '.join(related)}" if related else "Keine direkten Verknüpfungen"

        formatted_results.append(
            f"Chunk ID: {r['id']} (Score: {r['score']:.2f})\n"
            f"Titel: {r['title']} ({r['type']})\n"
            f"{related_str}\n"
            f"Inhalt: {r['content']}\n"
        )

    return "\n---\n".join(formatted_results)
