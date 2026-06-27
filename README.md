# Digital Sovereignty Agent

An AI agent for analyzing and evaluating the digital sovereignty of IT architectures. The system calculates sovereignty-reducing risks based on dependency chains within a Neo4j architecture graph.

## Features

- **Knowledge-Graph:** IT dependencies (microservices, databases, cloud providers) in a Neo4j graph.
- **Sovereignty Scoring:** Calculates risks based on four dimensions:
  - **Regulatory:** Server location / data residency.
  - **Geopolitics:** Legal jurisdiction (e.g., US CLOUD Act).
  - **Lock-In:** Degree of vendor lock-in (proprietary SaaS vs. open source).
  - **Contract:** Contract durations and flexibility.
- **Interactive Chat:** Web interface for conversations with the OpenAI based agent.

## Agent Tools

The agent is equipped with the following specific tools to solve user queries:

- `get_entity_score`: Calculates the detailed Digital Sovereignty Score for a specific entity.
- `read_evidence_chunk`: Reads raw evidence texts and contract snippets (TextChunks).
- `read_entity_description`: Retrieves detailed system or provider descriptions.
- `execute_cypher_query`: Autonomously generates and executes read-only Cypher queries against the Neo4j graph.
- `sparse_search`: Performs full-text keyword searches (BM25) across all TextChunks.

## Technology Stack

- **Backend:** Python, FastAPI, LangChain, LangGraph
- **Database:** Neo4j
- **Frontend:** Vanilla HTML / CSS / JavaScript
- **Infrastructure:** Docker & Docker Compose

## Setup & Installation

The project is fully containerized using Docker and can be started quickly.

### Prerequisites
- Docker and Docker Compose must be installed.
- An OpenAI API Key

### 1. Configure Environment Variables

Create a `.env` file in the root directory and add your OpenAI API key and Neo4j credentials:

```env
OPENAI_API_KEY=sk-your-api-key-here
NEO4J_USER=neo4j
NEO4J_PASSWORD=password
```

### 2. Start the Project

Build and start the containers using Docker Compose:

```bash
docker compose up --build
```

### 3. Initialize the Database

Once the containers are running, you must execute the following command once in the root directory to load the `data/graph_data.json` into the Neo4j graph:

```bash
docker compose exec backend python -m backend.init_db
```

### 4. Open the App

Now you can open the web interface in your browser:

**[http://localhost:8000](http://localhost:8000)**

*(The Neo4j Browser interface is available at [http://localhost:7474](http://localhost:7474))*

## Usage

In the chat, you can ask the agent natural language questions about your architecture. Examples:

- *"What is the sovereignty score for the Core Banking API?"*
- *"Are there any geopolitical risks regarding our HR systems?"*
- *"Show me all services that are hosted in the USA."*
- *"Search for 'Kündigungsfrist' in the provided contracts."*
