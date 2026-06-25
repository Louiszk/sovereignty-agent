import os
import sys
import logging

# Configure global logging for Docker
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

# Default to localhost for local testing.
# Inside Docker, docker-compose.yml overrides NEO4J_URI to "bolt://neo4j:7687"
NEO4J_URI = str(os.environ.get("NEO4J_URI", "bolt://localhost:7687"))
NEO4J_USER = str(os.environ.get("NEO4J_USER"))
NEO4J_PASSWORD = str(os.environ.get("NEO4J_PASSWORD"))

CYPHER_RECURSION_LIMIT = 8
