# SparkLens AI Agent - Low Level Design (LLD)

This document provides a detailed, code-level design of the **SparkLens AI Agent**, covering module architectures, class definitions, algorithms, data structures, and state management.

---

## 1. Class & Module Architecture

```mermaid
classDiagram
    class FastAPIApp {
        +lifespan(app)
        +index_page() FileResponse
        +get_new_thread() ThreadResponse
        +chat(request: ChatRequest) StreamingResponse
        +get_thread_history(thread_id: str) Dict
    }

    class DynamicSchemaCompiler {
        +json_schema_to_pydantic_model(model_name, schema) Type[BaseModel]
        +ensure_agent_compiled() CompiledGraph
    }

    class ContextVarSessionManager {
        +mcp_session_var: ContextVar[ClientSession]
        +make_call_tool(tool_name: str) Callable
    }

    class ChatRequest {
        +str message
        +Optional[str] thread_id
    }

    class ThreadResponse {
        +str thread_id
    }

    class EventStreamGenerator {
        +event_generator() AsyncGenerator
        -format_sse(payload: dict) str
    }

    FastAPIApp --> DynamicSchemaCompiler : invokes on startup & demand
    FastAPIApp --> ContextVarSessionManager : manages request scope
    FastAPIApp --> EventStreamGenerator : returns StreamingResponse
    FastAPIApp ..> ChatRequest : receives
    FastAPIApp ..> ThreadResponse : emits
```

---

## 2. Dynamic Schema Compiler Algorithm

The `json_schema_to_pydantic_model` function dynamically translates JSON Schema definitions emitted by the FastMCP server into typed Pydantic models required by LangChain's `StructuredTool.from_function`.

```mermaid
flowchart TD
    Start(["Input: tool.name, tool.inputSchema"]) --> ExtractProps["Extract properties and required list"]
    ExtractProps --> LoopFields{"Iterate over fields in properties"}
    
    LoopFields --> CheckAnyOf{"Is 'anyOf' present?"}
    CheckAnyOf -- Yes --> ParseUnion["Map each item type (string, int, float, bool, null) to Python types & build Union[...]"]
    CheckAnyOf -- No --> ParseSingle["Map type string (string->str, integer->int, etc.) to Python type"]
    
    ParseUnion --> CheckRequired{"Is field in required?"}
    ParseSingle --> CheckRequired
    
    CheckRequired -- Yes --> SetRequired["fields[name] = (field_type, Field(description=...))"]
    CheckRequired -- No --> SetOptional["fields[name] = (field_type, Field(default=..., description=...))"]
    
    SetRequired --> NextField["Next Field"]
    SetOptional --> NextField
    NextField --> LoopFields
    
    LoopFields -- Finished --> CreateModel["create_model(ModelName, **fields)"]
    CreateModel --> End(["Return Pydantic Model Class"])
```

### Key Python Implementation:
```python
def json_schema_to_pydantic_model(model_name: str, schema: Dict[str, Any]) -> Type[BaseModel]:
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
                if t_str == "string": types.append(str)
                elif t_str == "integer": types.append(int)
                elif t_str == "number": types.append(float)
                elif t_str == "boolean": types.append(bool)
                elif t_str == "null": types.append(type(None))
            field_type = Union[tuple(types)] if len(types) > 1 else (types[0] if types else Any)
        else:
            if type_str == "string": field_type = str
            elif type_str == "integer": field_type = int
            elif type_str == "number": field_type = float
            elif type_str == "boolean": field_type = bool
            elif type_str == "array": field_type = list
            elif type_str == "object": field_type = dict
                
        description = field_info.get("description", "")
        default = field_info.get("default", None)
        
        if field_name in required:
            fields[field_name] = (field_type, Field(description=description))
        else:
            fields[field_name] = (field_type, Field(default=default, description=description))
            
    return create_model(model_name, **fields)
```

---

## 3. Request-Local Session Isolation via `ContextVar`

To prevent cross-request contamination and idle timeout disconnects on persistent SSE connections:

```mermaid
flowchart TD
    Req["Incoming HTTP POST /api/chat"] --> SSEClient["async with sse_client(mcp_url) as streams"]
    SSEClient --> InitSession["async with ClientSession(...) as session: await session.initialize()"]
    InitSession --> SetToken["token = mcp_session_var.set(session)"]
    
    SetToken --> RunAgent["agent.astream_events(...)"]
    
    subgraph ToolInvocation["Tool Invocation during Agent Execution"]
        ToolCalled["LangChain Tool Wrapper invoked"] --> GetSession["session = mcp_session_var.get()"]
        GetSession --> CallMCP["await session.call_tool(tool_name, arguments)"]
        CallMCP --> ReturnResult["Return result.content to LangChain"]
    end
    
    RunAgent --> ToolInvocation
    RunAgent --> FinallyBlock["finally: mcp_session_var.reset(token)"]
    FinallyBlock --> ExitStreams["Exit context managers & close SSE streams"]
```

---

## 4. Streaming SSE Event Generator State Machine

```mermaid
stateDiagram-v2
    [*] --> EmitSetup: POST /api/chat
    EmitSetup --> StreamAgentEvents: Emit {"type": "setup", "thread_id": "..."}

    state StreamAgentEvents {
        [*] --> Listening
        Listening --> ToolStart: on_tool_start
        ToolStart --> Listening: Emit {"type": "tool_start", "name": ..., "arguments": ...}

        Listening --> ToolEnd: on_tool_end
        ToolEnd --> Listening: Emit {"type": "tool_end", "name": ...}

        Listening --> StreamChunk: on_chat_model_stream
        StreamChunk --> Listening: Emit {"type": "content", "delta": ...}

        Listening --> DoneState: Stream Exhausted
    }

    StreamAgentEvents --> Done: Emit {"type": "done"}
    StreamAgentEvents --> HandleError: Exception Caught
    HandleError --> [*]: Emit {"type": "error", "message": ...}
    Done --> [*]
```

---

## 5. Error Handling & Exception Management

```mermaid
flowchart TD
    TryBlock["Execute Request in event_generator"] --> ErrorCheck{"Exception Raised?"}
    ErrorCheck -- No --> Complete["Emit data: {'type': 'done'}"]
    
    ErrorCheck -- Yes --> CatchType{"Classify Exception"}
    
    CatchType --> MCPDown["ConnectError / TaskGroup Exception"]
    CatchType --> LLMQuota["Google GenAI RateLimit / Quota Exceeded"]
    CatchType --> SchemaErr["ValidationError"]
    CatchType --> GenericErr["General Exception"]
    
    MCPDown --> LogErr["Log ERROR & emit friendly JSON-SSE error message"]
    LLMQuota --> LogErr
    SchemaErr --> LogErr
    GenericErr --> LogErr
    
    LogErr --> CleanUp["Reset ContextVar & Close SSE Streams"]
    CleanUp --> End(["Terminate Stream Gracefully"])
```
