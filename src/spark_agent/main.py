import os
import logging
import sys
import json
import contextvars
from typing import Optional, List, Dict, Any, Type, Union
from pathlib import Path
from contextlib import asynccontextmanager

import dotenv
# Load .env from project root or current working directory
dotenv_path = Path(__file__).resolve().parents[2] / ".env"
if dotenv_path.exists():
    dotenv.load_dotenv(dotenv_path=str(dotenv_path))
else:
    dotenv.load_dotenv()

# Ensure GOOGLE_API_KEY is mapped from GEMINI_API_KEY
if "GEMINI_API_KEY" in os.environ and "GOOGLE_API_KEY" not in os.environ:
    os.environ["GOOGLE_API_KEY"] = os.environ["GEMINI_API_KEY"]

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, create_model

from langchain.agents import create_agent
from deepagents import create_deep_agent
from langchain_core.utils.uuid import uuid7
from langchain_core.tools import StructuredTool
from langgraph.checkpoint.memory import InMemorySaver
from mcp import ClientSession
from mcp.client.sse import sse_client

# CONSTANTS
SYSTEM_PROMPT = """You are a senior Apache Spark performance tuning and diagnostic AI engineer.
You are equipped with the SparkLens diagnostic toolkit. Your objective is to help developers analyze execution logs, identify performance issues, and troubleshoot Spark jobs.

Guidelines:
1. When asked about completed or running applications, use list_applications first.
2. For deep dives or general health analysis of a specific application, use analyze_application.
3. Diagnose failures by checking find_failed_stages, get_stages, or get_jobs.
4. Keep executor/stage skew or memory issue diagnostics in mind by checking get_executors or get_stage_details.
5. Provide helpful recommendations for Spark config optimization (e.g. parallelism, memory, partition sizes) if data skew or tasks overload is detected.
6. Present your analysis, logs, and findings in clean Markdown tables and use bolding/bullet points. Keep your responses structured and scannable.
"""

# Disable LangSmith tracing warnings if key is missing/invalid
os.environ.setdefault("LANGCHAIN_TRACING_V2", "false")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stderr
)
logger = logging.getLogger("spark-agent-backend")

checkpointer = InMemorySaver()
mcp_session_var = contextvars.ContextVar("mcp_session")

# Global placeholders
agent = None

def json_schema_to_pydantic_model(model_name: str, schema: Dict[str, Any]) -> Type[BaseModel]:
    """Dynamically converts a JSON Schema to a Pydantic BaseModel."""
    fields = {}
    properties = schema.get("properties", {})
    required = schema.get("required", [])
    
    for field_name, field_info in properties.items():
        field_type: Any = Any
        type_str = field_info.get("type")
        
        if "anyOf" in field_info:
            types = []
            for t in field_info["anyOf"]:
                t_str = t.get("type")
                if t_str == "string":
                    types.append(str)
                elif t_str == "integer":
                    types.append(int)
                elif t_str == "number":
                    types.append(float)
                elif t_str == "boolean":
                    types.append(bool)
                elif t_str == "null":
                    types.append(type(None))
            field_type = Union[tuple(types)] if len(types) > 1 else (types[0] if types else Any)
        else:
            if type_str == "string":
                field_type = str
            elif type_str == "integer":
                field_type = int
            elif type_str == "number":
                field_type = float
            elif type_str == "boolean":
                field_type = bool
            elif type_str == "array":
                field_type = list
            elif type_str == "object":
                field_type = dict
                
        description = field_info.get("description", "")
        default = field_info.get("default", None)
        
        if field_name in required:
            fields[field_name] = (field_type, Field(description=description))
        else:
            fields[field_name] = (field_type, Field(default=default, description=description))
            
    return create_model(model_name, **fields)

async def ensure_agent_compiled():
    """Ensure LangChain agent is compiled with tools from the MCP server."""
    global agent
    if agent is not None:
        return agent
        
    mcp_url = os.getenv("SPARK_MCP_URL", "http://localhost:8030/sse")
    logger.info(f"Connecting to SparkLens MCP SSE server at {mcp_url} for compilation...")
    
    async with sse_client(mcp_url) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            logger.info("Connected to MCP server. Fetching available tools for agent compilation...")
            
            tools_response = await session.list_tools()
            langchain_tools = []
            
            def make_call_tool(tool_name):
                async def call_tool(**kwargs):
                    # Filter out None values to let the MCP server apply defaults
                    cleaned_args = {k: v for k, v in kwargs.items() if v is not None}
                    # Get active request-scoped session from ContextVar
                    session = mcp_session_var.get()
                    logger.info(f"Forwarding call to MCP: {tool_name} with args {cleaned_args}")
                    result = await session.call_tool(tool_name, arguments=cleaned_args)
                    return result.content
                return call_tool

            for tool in tools_response.tools:
                # Construct unique input class name
                model_name = "".join(x.capitalize() for x in tool.name.split("_")) + "Input"
                args_schema = json_schema_to_pydantic_model(model_name, tool.inputSchema)
                
                lc_tool = StructuredTool.from_function(
                    coroutine=make_call_tool(tool.name),
                    name=tool.name,
                    description=tool.description,
                    args_schema=args_schema
                )
                langchain_tools.append(lc_tool)
                logger.info(f"Compiled LangChain tool wrapper: {tool.name}")
            
            DEFAULT_MODEL = os.getenv("AGENT_MODEL", "google_genai:gemini-3.1-flash-lite")
            logger.info(f"Creating LangChain agent with model: {DEFAULT_MODEL}...")
            
            agent = create_deep_agent(
                model=DEFAULT_MODEL,
                tools=langchain_tools,
                checkpointer=checkpointer,
                system_prompt=SYSTEM_PROMPT
            )
            logger.info("LangChain Spark Agent successfully compiled and ready.")
            return agent

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Attempts to compile the LangChain agent graph on startup if MCP server is available."""
    try:
        await ensure_agent_compiled()
    except Exception as e:
        logger.warning(f"Could not connect to SparkLens MCP server at startup ({e}). Will attempt compilation on first request.")
        
    yield
    logger.info("Service shutting down.")

app = FastAPI(
    title="SparkLens AI Agent API & UI",
    description="FastAPI backend serving a LangChain agent connected to a SparkLens MCP Server.",
    version="0.1.0",
    lifespan=lifespan
)

STATIC_DIR = Path(__file__).parent / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

class ChatRequest(BaseModel):
    message: str = Field(..., description="User message prompt")
    thread_id: Optional[str] = Field(None, description="Thread UUID to maintain conversation history")

class ChatResponse(BaseModel):
    response: str
    thread_id: str

class ThreadResponse(BaseModel):
    thread_id: str

@app.get("/api/new_thread", response_model=ThreadResponse)
def get_new_thread():
    """Generates a new unique thread ID."""
    return ThreadResponse(thread_id=str(uuid7()))

def extract_text_from_content(content: Any) -> str:
    """Extract clean string content from string, list of blocks, or dict."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        text_parts = []
        for part in content:
            if isinstance(part, str):
                text_parts.append(part)
            elif isinstance(part, dict):
                if part.get("type") == "text" and "text" in part:
                    text_parts.append(part["text"])
                elif "text" in part:
                    text_parts.append(str(part["text"]))
            elif hasattr(part, "text"):
                text_parts.append(str(part.text))
        if text_parts:
            return "\n".join(text_parts)
    if isinstance(content, dict):
        if "text" in content:
            return str(content["text"])
    return str(content)

@app.post("/api/chat")
async def chat(request: ChatRequest):
    """Sends a message to the agent and gets a streaming response over SSE."""
    try:
        await ensure_agent_compiled()
    except Exception as e:
        logger.error(f"Failed to connect to MCP server: {e}")
        raise HTTPException(
            status_code=503,
            detail=f"Cannot connect to SparkLens MCP server. Ensure it is running at {os.getenv('SPARK_MCP_URL', 'http://localhost:8030/sse')}."
        )
        
    if not request.message or not request.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    thread_id = request.thread_id.strip() if request.thread_id else str(uuid7())
    config = {"configurable": {"thread_id": thread_id}}

    async def event_generator():
        mcp_url = os.getenv("SPARK_MCP_URL", "http://localhost:8030/sse")
        logger.info(f"Establishing dynamic request-local MCP session to {mcp_url}...")
        
        try:
            # Yield setup event first so frontend gets the thread ID
            yield f"data: {json.dumps({'type': 'setup', 'thread_id': thread_id})}\n\n"
            
            async with sse_client(mcp_url) as (read_stream, write_stream):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    logger.info("Request-local MCP session initialized.")
                    
                    # Store session in ContextVar
                    token = mcp_session_var.set(session)
                    try:
                        async for event in agent.astream_events(
                            {"messages": [{"role": "user", "content": request.message.strip()}]},
                            config=config,
                            version="v2"
                        ):
                            kind = event["event"]
                            name = event["name"]
                            
                            if kind == "on_chat_model_stream":
                                chunk = event["data"]["chunk"]
                                if hasattr(chunk, "content") and chunk.content:
                                    content_val = chunk.content
                                    if isinstance(content_val, list):
                                        for part in content_val:
                                            if isinstance(part, dict) and "text" in part:
                                                yield f"data: {json.dumps({'type': 'content', 'delta': part['text']})}\n\n"
                                            elif hasattr(part, "text"):
                                                yield f"data: {json.dumps({'type': 'content', 'delta': part.text})}\n\n"
                                            elif isinstance(part, str):
                                                yield f"data: {json.dumps({'type': 'content', 'delta': part})}\n\n"
                                    elif isinstance(content_val, str):
                                        yield f"data: {json.dumps({'type': 'content', 'delta': content_val})}\n\n"
                            
                            elif kind == "on_tool_start":
                                inputs = event["data"].get("input", {})
                                yield f"data: {json.dumps({'type': 'tool_start', 'name': name, 'arguments': inputs})}\n\n"
                            
                            elif kind == "on_tool_end":
                                yield f"data: {json.dumps({'type': 'tool_end', 'name': name})}\n\n"
                                
                        yield f"data: {json.dumps({'type': 'done'})}\n\n"
                    finally:
                        mcp_session_var.reset(token)

        except Exception as e:
            logger.error(f"Error during request-local agent streaming: {e}", exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")

@app.get("/api/history/{thread_id}")
async def get_thread_history(thread_id: str):
    """Retrieves conversation history for a thread."""
    global agent
    if not agent:
        raise HTTPException(status_code=503, detail="Agent is not initialized.")
        
    config = {"configurable": {"thread_id": thread_id}}
    try:
        state = await agent.aget_state(config)
        messages_data = []
        if state and state.values and "messages" in state.values:
            for msg in state.values["messages"]:
                role = "assistant"
                content = ""
                if hasattr(msg, "type"):
                    role = "user" if msg.type in ("human", "user") else "assistant"
                elif hasattr(msg, "role"):
                    role = msg.role
                
                if hasattr(msg, "content"):
                    content = msg.content
                elif isinstance(msg, dict):
                    content = msg.get("content", "")

                messages_data.append({"role": role, "content": str(content)})

        return {"thread_id": thread_id, "messages": messages_data}
    except Exception as e:
        return {"thread_id": thread_id, "messages": [], "error": str(e)}

@app.get("/", response_class=HTMLResponse)
def index_page():
    """Serves the web chat application UI."""
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return HTMLResponse("<h1>SparkLens Agent API Server</h1><p>UI file index.html not found.</p>")

def run():
    """CLI entry point to launch the Uvicorn server."""
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    host = os.getenv("HOST", "0.0.0.0")
    uvicorn.run("spark_agent.main:app", host=host, port=port, reload=True)

if __name__ == "__main__":
    run()
