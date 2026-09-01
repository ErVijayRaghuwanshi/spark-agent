# SparkLens AI Agent - Architecture Overview

This document outlines the end-to-end system architecture of the **SparkLens AI Agent**, explaining how client interfaces, agentic reasoning models, dynamic tool bridges, and Apache Spark diagnostic clusters interact.

---

## 1. High-Level System Architecture

The SparkLens AI Agent is designed as a decoupled, multi-tiered AI diagnostic application. It bridges LLM reasoning with live Apache Spark execution data via the Model Context Protocol (MCP).

```mermaid
flowchart TB
    subgraph ClientTier["User & Presentation Tier"]
        UI["Web Dashboard (TailwindCSS + Marked.js)"]
        CLI["CLI / Terminal Client"]
    end

    subgraph BackendTier["FastAPI Application Tier"]
        API["FastAPI REST & SSE Router (/api/chat, /api/history)"]
        StaticSrv["Static File Server (/static)"]
        CV["ContextVar Manager (Request-Local Session Scope)"]
    end

    subgraph AgentTier["Agentic Reasoning Tier"]
        LLM["Google Gemini Model (gemini-3.1-flash-lite / pro)"]
        LangGraph["LangGraph DeepAgent Engine"]
        Memory["InMemorySaver (Thread Checkpointer)"]
        ToolRegistry["Dynamic LangChain Tool Registry"]
    end

    subgraph MCPBridge["Model Context Protocol (MCP) Tier"]
        MCPClient["MCP SSE Async Client (ClientSession)"]
        FastMCPServer["SparkLens MCP Server (FastMCP SSE :8030)"]
    end

    subgraph SparkTier["Apache Spark Observability Tier"]
        SHS["Spark History Server (:18080)"]
        Master["Spark Master / Driver Metrics (:4040)"]
        Livy["Livy Server / Spark Connect Endpoint"]
    end

    UI -->|"SSE / HTTP POST"| API
    CLI -->|"HTTP POST"| API
    API -->|"Static Assets"| StaticSrv
    API -->|"Scoped MCP Context"| CV
    API -->|"Execute Stream"| LangGraph
    
    LangGraph <-->|"Reasoning & Tool Selection"| LLM
    LangGraph <-->|"Thread State"| Memory
    LangGraph -->|"Invoke Tool"| ToolRegistry

    ToolRegistry -->|"Routed via ContextVar"| MCPClient
    MCPClient <-->|"JSON-RPC over SSE"| FastMCPServer
    FastMCPServer <-->|"REST API Queries"| SHS
    FastMCPServer <-->|"Metrics & Web UI Scrapes"| Master
    FastMCPServer <-->|"Session Introspection"| Livy
```

---

## 2. End-to-End Request & Streaming Sequence

When a user submits a question or diagnostic command, the backend establishes a request-local MCP connection, streams thoughts and tool invocations to the UI, and cleans up sockets upon completion.

```mermaid
sequenceDiagram
    autonumber
    actor User as User / Browser
    participant API as FastAPI (/api/chat)
    participant Agent as LangGraph Agent
    participant LLM as Gemini Model
    participant MCP as MCP SSE Client
    participant Server as SparkLens MCP Server
    participant SHS as Spark History Server

    User->>API: POST /api/chat { message: "Why did stage 3 fail?", thread_id: "..." }
    API->>MCP: Establish fresh SSE connection (http://localhost:8030/sse)
    MCP-->>API: Active ClientSession
    API->>API: Set mcp_session_var ContextVar
    API-->>User: data: {"type": "setup", "thread_id": "..."}

    API->>Agent: astream_events(message, config)
    Agent->>LLM: Send user prompt + available tool schemas
    LLM-->>Agent: Function Call Request: find_failed_stages(app_id="app-123")
    
    Agent-->>API: event: on_tool_start (find_failed_stages)
    API-->>User: data: {"type": "tool_start", "name": "find_failed_stages", "arguments": {...}}
    
    Agent->>MCP: call_tool("find_failed_stages", {"app_id": "app-123"})
    MCP->>Server: JSON-RPC Call: find_failed_stages
    Server->>SHS: GET /api/v1/applications/app-123/stages
    SHS-->>Server: JSON Stage Metrics & Failure Reason
    Server-->>MCP: Tool Content Result
    MCP-->>Agent: Raw Execution & Failure Diagnostics

    Agent-->>API: event: on_tool_end (find_failed_stages)
    API-->>User: data: {"type": "tool_end", "name": "find_failed_stages"}

    Agent->>LLM: Provide tool output for final synthesis
    loop Token Streaming
        LLM-->>Agent: Stream token delta
        Agent-->>API: event: on_chat_model_stream (delta)
        API-->>User: data: {"type": "content", "delta": "Stage 3 failed due to OOM..."}
    end

    Agent-->>API: Stream completed
    API-->>User: data: {"type": "done"}
    API->>MCP: Close SSE connection & reset ContextVar
```

---

## 3. Dynamic Tool Compilation Pipeline

The agent does not hardcode any MCP tool wrappers. Instead, tools are inspected, converted into Pydantic models at runtime, and registered into LangChain:

```mermaid
flowchart LR
    A["SparkLens MCP Server"] -->|"session.list_tools()"| B["Tool Definitions (JSON Schema)"]
    B -->|"json_schema_to_pydantic_model()"| C["Dynamic Pydantic Input Models"]
    C -->|"StructuredTool.from_function()"| D["LangChain StructuredTools"]
    D -->|"ContextVar Bridge"| E["Thread-Safe Tool Invocation"]
    E -->|"create_deep_agent()"| F["Compiled LangGraph Executable Graph"]
```

---

## 4. Connection Concurrency & ContextVar Lifecycle

To prevent HTTP/SSE keep-alive timeouts (`ClosedResourceError` or `RemoteProtocolError`), each concurrent request lifecycle is strictly isolated:

```mermaid
stateDiagram-v2
    [*] --> RequestReceived: POST /api/chat
    RequestReceived --> ConnectMCP: Open sse_client()
    ConnectMCP --> SetContextVar: mcp_session_var.set(session)
    SetContextVar --> StreamEvents: astream_events()
    
    state StreamEvents {
        [*] --> ModelThinking
        ModelThinking --> ToolExecution: Tool Call Requested
        ToolExecution --> ToolFetchSession: mcp_session_var.get()
        ToolFetchSession --> ExecuteOnMCP: session.call_tool()
        ExecuteOnMCP --> ModelThinking: Return Tool Output
        ModelThinking --> YieldTokens: Stream Content Chunks
        YieldTokens --> [*]
    }
    
    StreamEvents --> ResetContextVar: finally block
    ResetContextVar --> CloseConnection: exit sse_client context
    CloseConnection --> [*]: Request Finished Cleanly
```

---

## 5. Technology Stack Summary

| Layer | Component | Description |
| :--- | :--- | :--- |
| **Frontend** | HTML5, Tailwind CSS, Marked.js | Lightweight responsive web UI with real-time SSE parsing |
| **API Server** | FastAPI, Uvicorn, Starlette | Asynchronous web framework serving REST and SSE endpoints |
| **AI / Agent Engine**| LangChain, LangGraph, DeepAgents | Agent workflow orchestration, memory checkpointing, and tool loop |
| **LLM Provider** | Google GenAI (`gemini-3.1-flash-lite`) | High-throughput, low-latency reasoning and diagnostic synthesis |
| **Tool Protocol** | Model Context Protocol (MCP), FastMCP | Standardized AI-to-tool client-server SSE communication |
| **Target Engine** | Apache Spark 3.x / 4.x | Spark History Server, Spark Connect, and driver metrics |
