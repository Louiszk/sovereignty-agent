import os
import sys
import logging

# Configure global logging for Docker
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

# Silence Neo4j schema warnings
logging.getLogger("neo4j.notifications").setLevel(logging.ERROR)

# Inside Docker, docker-compose.yml overrides NEO4J_URI to "bolt://neo4j:7687"
NEO4J_URI = str(os.environ.get("NEO4J_URI", "bolt://localhost:7687"))
NEO4J_USER = str(os.environ.get("NEO4J_USER"))
NEO4J_PASSWORD = str(os.environ.get("NEO4J_PASSWORD"))

CYPHER_DEPTH_LIMIT = 8
AGENT_RECURSION_LIMIT = 15
