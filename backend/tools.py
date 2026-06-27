from typing import cast, LiteralString
import json
import neo4j.exceptions
import tiktoken
from neo4j import GraphDatabase, unit_of_work
from backend.config import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, CYPHER_DEPTH_LIMIT
import logging
from langchain_openai import OpenAIEmbeddings

logger = logging.getLogger(__name__)
encoder = tiktoken.get_encoding("o200k_base")

driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))


def calculate_sovereignty_score(entity_id: str) -> str:
    """
    Calculates the digital sovereignty score for an entity using a multiplicative model
    with depth decay and criticality weighting.
    """
    logger.info(f"Calculating sovereignty score for entity_id: {entity_id}")
    query = cast(
        LiteralString,
        f"""
        MATCH path = (s {{id: $entity_id}})-[:DEPENDS_ON|RUNS_ON*1..{CYPHER_DEPTH_LIMIT}]->(target)
        WHERE NOT 'TextChunk' IN labels(s) AND NOT 'TextChunk' IN labels(target)
        WITH s.name AS entity_name, 
             last(relationships(path)) AS rel, 
             length(path) AS depth, 
             startNode(last(relationships(path))) AS source, 
             target
        WITH entity_name, rel, source, target, min(depth) AS min_depth
        RETURN entity_name, collect(DISTINCT {{
            rel: rel,
            target_id: target.id,
            target_name: target.name,
            target_is_internal: coalesce(target.is_internal, false),
            depth: min_depth,
            source_id: source.id,
            source_name: source.name,
            source_criticality: source.criticality
        }}) AS distinct_rels
        """,
    )

    with driver.session() as session:
        result = session.run(query, entity_id=entity_id).single()

    if not result:
        check_query = cast(LiteralString, "MATCH (s {id: $entity_id}) WHERE NOT s:TextChunk RETURN s.name AS name")
        with driver.session() as session:
            check = session.run(check_query, entity_id=entity_id).single()
        if check:
            return f"Souveränitäts-Score für {check['name']}: 100.0/100\nKeine Abhängigkeiten gefunden."
        return f"Entity mit ID {entity_id} nicht gefunden."

    entity_name = result["entity_name"]
    rels = result["distinct_rels"]

    dimensions = {"Regulatorik": 1.0, "Geopolitik": 1.0, "Lock_In": 1.0, "Vertrag": 1.0}
    weights = {"Regulatorik": 0.3, "Geopolitik": 0.3, "Lock_In": 0.2, "Vertrag": 0.2}
    decay_bases = {"Regulatorik": 0.8, "Geopolitik": 0.8, "Lock_In": 0.6, "Vertrag": 0.6}

    red_flags = []
    risk_details = []

    valid_rels = [r for r in rels if r and r.get("rel")]
    valid_rels.sort(key=lambda x: x.get("depth", 1))

    for item in valid_rels:
        rel = item["rel"]
        target_name = item.get("target_name", "Unbekannt")
        is_internal = item.get("target_is_internal", False)
        depth = item.get("depth", 1)

        ownership_str = "Internes Asset" if is_internal else "Externer Provider/SaaS"
        target_display = f"{target_name} ({ownership_str})"

        chunk_id = rel.get("provenance_chunk_id")
        chunk_ref = f" [[{chunk_id}]]" if chunk_id else ""

        decays = {k: v ** (depth - 1) for k, v in decay_bases.items()}
        crit_str = item.get("source_criticality", "High")
        crit_factor = 1.0 if crit_str == "High" else (0.6 if crit_str == "Medium" else 0.3)

        dep_mode = rel.get("dependency_mode", "required")
        dep_factor = (
            1.0
            if dep_mode == "required"
            else (0.7 if dep_mode == "degraded" else (0.3 if dep_mode == "optional" else 0.1))
        )

        residency = rel.get("data_residency")
        if residency == "USA":
            effective_risk = 0.40 * decays["Regulatorik"] * crit_factor * dep_factor
            dimensions["Regulatorik"] *= 1 - effective_risk

            red_flags.append(f"Datenresidenz USA bei '{target_display}' (Distanz: {depth}){chunk_ref}")
            risk_details.append(
                f"- [Regulatorik] Daten in den USA bei '{target_display}' (Tiefe {depth}, Modus: {dep_mode}). Score-Abzug: {effective_risk * 100:.1f}%{chunk_ref}"
            )

        jurisdiction = rel.get("jurisdiction")
        if jurisdiction == "USA":
            effective_risk = 0.40 * decays["Geopolitik"] * crit_factor * dep_factor
            dimensions["Geopolitik"] *= 1 - effective_risk

            red_flags.append(f"US-Jurisdiktion (z.B. CLOUD Act) bei '{target_display}' (Distanz: {depth}){chunk_ref}")
            risk_details.append(
                f"- [Geopolitik] US-Jurisdiktion bei '{target_display}' (Tiefe {depth}, Modus: {dep_mode}). Score-Abzug: {effective_risk * 100:.1f}%{chunk_ref}"
            )

        lock_in = rel.get("lock_in_level")
        if lock_in == "High":
            effective_risk = 0.30 * decays["Lock_In"] * crit_factor * dep_factor
            dimensions["Lock_In"] *= 1 - effective_risk
            risk_details.append(
                f"- [Lock-In] Hoher Vendor-Lock-In bei '{target_display}' (Tiefe {depth}, Modus: {dep_mode}). Score-Abzug: {effective_risk * 100:.1f}%{chunk_ref}"
            )
        elif lock_in == "Medium":
            effective_risk = 0.10 * decays["Lock_In"] * crit_factor * dep_factor
            dimensions["Lock_In"] *= 1 - effective_risk
            risk_details.append(
                f"- [Lock-In] Mittlerer Vendor-Lock-In bei '{target_display}' (Tiefe {depth}, Modus: {dep_mode}). Score-Abzug: {effective_risk * 100:.1f}%{chunk_ref}"
            )

        duration = rel.get("contract_duration_months")
        if duration is not None:
            if duration >= 24:
                effective_risk = 0.20 * decays["Vertrag"] * crit_factor * dep_factor
                dimensions["Vertrag"] *= 1 - effective_risk
                risk_details.append(
                    f"- [Vertrag] Lange Vertragslaufzeit ({duration} Mon.) bei '{target_display}' (Tiefe {depth}, Modus: {dep_mode}). Score-Abzug: {effective_risk * 100:.1f}%{chunk_ref}"
                )
            elif duration >= 13:
                effective_risk = 0.10 * decays["Vertrag"] * crit_factor * dep_factor
                dimensions["Vertrag"] *= 1 - effective_risk
                risk_details.append(
                    f"- [Vertrag] Erhöhte Vertragslaufzeit ({duration} Mon.) bei '{target_display}' (Tiefe {depth}, Modus: {dep_mode}). Score-Abzug: {effective_risk * 100:.1f}%{chunk_ref}"
                )

    overall_score = sum(dimensions[k] * weights[k] for k in dimensions) * 100

    # Report formatieren
    report = f"Souveränitäts-Score für {entity_name}: {overall_score:.1f}/100\n"

    report += "\nDimensionen:"
    for k, v in dimensions.items():
        report += f"\n- {k}: {v * 100:.1f}/100"

    if red_flags:
        unique_flags = sorted(list(set(red_flags)))
        report += "\n\nKritische Risiken:\n" + "\n".join(f"- {flag}" for flag in unique_flags)

    if risk_details:
        report += "\n\nDetail-Auswertung der Architektur:\n" + "\n".join(risk_details)
    else:
        report += "\n\nDetail-Auswertung: Keine souveränitätsmindernden Abhängigkeiten identifiziert."

    logger.info(f"Score for {entity_id} calculated as {overall_score:.1f}")
    return report


def get_chunk_content(chunk_id: str) -> str:
    """
    Retrieves the raw text content and type of a TextChunk by its ID.
    """
    from backend.utils import get_chunk_data

    logger.info(f"Retrieving chunk content for chunk_id: {chunk_id}")
    data = get_chunk_data(chunk_id)

    if not data:
        return f"TextChunk mit ID {chunk_id} nicht gefunden."

    source_info = f"\nQuelle: {data['source_file']}" if data.get("source_file") else ""
    return f"Titel: {data.get('title', 'Kein Titel')}\nTyp: {data['type']}{source_info}\nInhalt: {data['content']}"


def get_entity_description(entity_id: str) -> str:
    """
    Retrieves the description TextChunks for a given entity ID.
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
        results = session.run(query, entity_id=entity_id).data()

    if not results:
        return f"Keine Beschreibung (TextChunk) für Entity ID {entity_id} gefunden."

    descriptions = []
    for result in results:
        descriptions.append(
            f"Chunk ID: {result['id']}\nTitel: {result.get('title', 'Kein Titel')}\nBeschreibung: {result['content']}"
        )

    return "\n\n".join(descriptions)


def execute_custom_cypher(query: str) -> str:
    """
    Executes a custom read-only Cypher query against the Neo4j database.
    Guardrails: 20s timeout, read-only enforcement, max 80,000 tokens output.
    """
    logger.info(f"Executing custom Cypher: {query}")

    # Simple static check for obvious write commands
    upper_query = query.upper()
    if any(
        forbidden in upper_query for forbidden in ["CREATE", "SET", "DELETE", "REMOVE", "DROP", "MERGE", "CALL APOC"]
    ):
        return "FEHLER: Schreiboperationen sind aus Sicherheitsgründen in diesem Tool blockiert."

    @unit_of_work(timeout=20.0)
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
        results = _run_query()

        if not results:
            return (
                "Die Cypher-Query wurde erfolgreich ausgeführt, hat aber keine Ergebnisse geliefert (leere Rückgabe)."
            )

        json_output = json.dumps(results, ensure_ascii=False, default=str)

        # Check Token Limit using tiktoken (max 80,000 tokens)
        token_count = len(encoder.encode(json_output))
        if token_count > 80000:
            return f"FEHLER: Das Ergebnis ist zu groß ({token_count} Tokens). Das Token-Limit (80k Tokens) wurde überschritten. Bitte aggregiere die Daten (z.B. mit count()) oder setze ein striktes LIMIT."

        return json_output

    except neo4j.exceptions.ClientError as e:
        logger.error(f"Cypher Syntax/Client Error: {e}")
        return f"FEHLER in der Cypher-Query: {e}"
    except Exception as e:
        logger.error(f"Execution Error: {e}")
        return f"FEHLER bei der Ausführung: {e}"


def keyword_search(keywords: list[str]) -> str:
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
        RETURN node.id AS id, node.title AS title, node.type AS type, node.content AS content, node.source_file AS source_file, score
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

        source_info = f"\nQuelle: {r['source_file']}" if r.get("source_file") else ""
        formatted_results.append(
            f"Chunk ID: {r['id']} (Score: {r['score']:.2f})\n"
            f"Titel: {r['title']} ({r['type']}){source_info}\n"
            f"{related_str}\n"
            f"Inhalt: {r['content']}\n"
        )

    return "\n---\n".join(formatted_results)


def vector_search(query: str) -> str:
    """
    Executes a semantic vector search across document embeddings.
    Requires an embedding model (e.g., text-embedding-3-small) and vector index setup in Neo4j.
    """
    if not query:
        return "FEHLER: Keine Suchanfrage angegeben."

    logger.info(f"Executing dense search for: {query}")

    try:
        embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
        query_embedding = embeddings.embed_query(query)
    except Exception as e:
        logger.error(f"Error generating embedding: {e}")
        return f"FEHLER beim Generieren des Embeddings: {e}"

    cypher_query = cast(
        LiteralString,
        """
        CALL db.index.vector.queryNodes("vector_index", 3, $query_embedding) YIELD node, score
        RETURN node.id AS id, node.title AS title, node.type AS type, node.content AS content, node.source_file AS source_file, score
        """,
    )

    try:
        with driver.session() as session:
            result = session.run(cypher_query, query_embedding=query_embedding).data()

        if not result:
            return f"Keine relevanten Dokumente für die Suchanfrage '{query}' gefunden."

        formatted_results = []
        for r in result:
            connected_query = cast(
                LiteralString,
                "MATCH (c:TextChunk {id: $chunk_id})-[:RELATES_TO|DESCRIBED_BY]-(related) RETURN collect(related.name) AS related_entities",
            )
            with driver.session() as session:
                conn_res = session.run(connected_query, chunk_id=r["id"]).single()

            related = conn_res["related_entities"] if conn_res else []
            related_str = f"Verknüpft mit: {', '.join(related)}" if related else "Keine direkten Verknüpfungen"

            source_info = f"\nQuelle: {r['source_file']}" if r.get("source_file") else ""
            formatted_results.append(
                f"Chunk ID: {r['id']} (Score: {r['score']:.2f})\n"
                f"Titel: {r['title']} ({r['type']}){source_info}\n"
                f"{related_str}\n"
                f"Inhalt: {r['content']}\n"
            )

        return "\n---\n".join(formatted_results)
    except Exception as e:
        logger.error(f"Execution Error during vector search: {e}")
        return f"FEHLER bei der Ausführung der Vektorsuche: {e}"
