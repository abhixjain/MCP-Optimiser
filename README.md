Here’s a shorter, clean version of your **README.md**:

---

# MCP Optimiser

MCP Optimiser is a lightweight orchestration layer that aggregates tools from multiple MCP servers and exposes two agent-safe tools:

* `find_tool` – Discover tools with name, description, and schema
* `call_tool` – Execute tools using structured JSON arguments

It prevents tool-name hallucination and enforces a reliable **discover → execute** workflow.

---

## How It Works

### MCPToolRegistry

* Indexes tools from live MCP clients
* Preserves active sessions
* Supports keyword-based search
* Provides prompt-ready summaries

### Tool Factory

`_make_tools(registry)` generates:

* 🔍 `find_tool(query)`
* ⚙️ `call_tool(tool_name, arguments)`

`call_tool` invokes the exact tool through the live MCP session and safely extracts structured output.

---

## Built With Strands Agents

This implementation uses `strands.Agent` and the `@tool` decorator, but the architecture is framework-agnostic.

You can easily adapt it to:

* LangChain
* OpenAI tool calling
* LlamaIndex
* Autogen
* Custom agent runtimes

Only the tool registration layer needs modification.

---

## Why Use It?

* Reduces tool hallucination
* Enforces schema-aware execution
* Works across multiple MCP servers
* Keeps agent-tool integration clean and scalable


