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

# Define risk metrics configuration for score evaluation
METRIC_CONFIGS = [
    {
        "property": "data_residency",
        "is_numeric": False,
        "rules": [
            {
                "match": "USA",
                "penalty": 25,
                "msg": "Datenhaltung oder Verarbeitung außerhalb der EU (USA) im Abhängigkeitsbaum.",
            }
        ],
    },
    {
        "property": "lock_in_level",
        "is_numeric": False,
        "rules": [
            {"match": "High", "penalty": 15, "msg": "Hoher Vendor-Lock-in in der Abhängigkeitskette gefunden."},
            {"match": "Medium", "penalty": 5, "msg": "Mittlerer Vendor-Lock-in in der Abhängigkeitskette gefunden."},
        ],
    },
    {
        "property": "contract_duration_months",
        "is_numeric": True,
        "rules": [
            {"min_val": 24, "penalty": 10, "msg": "Lange Vertragslaufzeit/Kündigungsfrist ({val} Monate) im Pfad."},
            {"min_val": 13, "penalty": 5, "msg": "Erhöhte Vertragslaufzeit ({val} Monate) im Pfad."},
        ],
    },
]
