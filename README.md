# SparkLens AI Agent ⚡

An AI-powered diagnostic and performance observability assistant for Apache Spark. 

The agent connects dynamically to the **SparkLens MCP Server** using the Model Context Protocol (MCP) and SSE transport, empowering developers to diagnose slow stages, detect data skew, troubleshoot failed queries, inspect JVM/environment parameters, and optimize resource allocation.

---

## 📚 Documentation & Design

- 🏛️ **[System Architecture](docs/architecture.md):** End-to-end architecture diagrams, dynamic schema compilation pipeline, and sequence diagrams.
- 📐 **[High-Level Design (HLD)](docs/hld.md):** Subsystem decomposition, streaming protocol, and non-functional requirements.
- 🔬 **[Low-Level Design (LLD)](docs/lld.md):** Detailed module structure, Pydantic type compiler algorithm, ContextVar lifecycle, and error handling.
- 🗺️ **[Project Roadmap](docs/roadmap.md):** Milestones, live cluster integration plans, and future feature tracks.

---

## 📁 Project Structure

```text
spark-agent/
├── pyproject.toml              # UV / Package configuration and dependencies
├── .python-version             # Python version (>=3.11)
├── .env.example                # Example environment variables template
├── .env                        # Local environment configuration
├── .gitignore                  # Git ignore rules
├── LICENSE                     # Apache 2.0 License
├── README.md                   # Documentation
├── docs/                       # Architectural and design specifications
│   ├── architecture.md
│   ├── hld.md
│   ├── lld.md
│   └── roadmap.md
└── src/
    └── spark_agent/
        ├── __init__.py
        ├── main.py             # FastAPI backend with dynamic MCP tool bridge & streaming
        └── static/
            └── index.html      # Responsive Dark-themed Diagnostic Dashboard UI
```

---

## 🚀 Quick Start

### 1. Clone the Repository

```bash
git clone https://github.com/ErVijayRaghuwanshi/spark-agent.git
cd spark-agent
```

### 2. Configure Environment

Ensure your `.env` contains your Gemini API key and points to your running SparkLens MCP server:

```env
GEMINI_API_KEY=your_gemini_api_key_here
SPARK_MCP_URL=http://localhost:8030/sse
AGENT_MODEL=google_genai:gemini-3.1-flash-lite
```

### 3. Start SparkLens MCP Server

In your `spark-lens` repository, ensure the FastMCP server is active:

```bash
cd /Users/ervijay/Documents/Programs/Repo/spark-lens
uv run --env-file .env python -m sparklens.server
```

### 4. Run the Spark Agent

From the `spark-agent` directory:

```bash
uv run uvicorn spark_agent.main:app --reload --port 8000
```

Or using the CLI entrypoint:

```bash
uv run spark-agent
```

### 5. Open the Web Dashboard

Open your browser and navigate to:
👉 **[http://127.0.0.1:8000](http://127.0.0.1:8000)**

---

## 🔍 Features

- **Real-Time Streaming & Live Tool Execution:** Token-by-token streaming with live tool-calling visual pills in the chat.
- **Dynamic Tool Registration:** On startup, dynamically queries the MCP server and compiles LangChain/DeepAgent tools from JSON schemas without hardcoded mappings.
- **Request-Local Sessions:** Uses async `contextvars` to manage dedicated, leak-free SSE connections per user request, preventing socket timeouts and disconnections.
- **Full Spark History Diagnostics:** Deep analysis of Spark Applications, Jobs, Stages, Executors, SQL execution plans, WholeStageCodegen, and Data Skew.

---

## 📜 License

This project is licensed under the Apache License 2.0 - see the [LICENSE](LICENSE) file for details.
