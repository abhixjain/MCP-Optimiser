from __future__ import annotations
 
import re
import json
import uuid
from datetime import datetime
from typing import Any
 
from strands import Agent
from strands.tools import tool as strands_tool
 
 
# ─────────────────────────────────────────────────────────────────────────────
# 1.  MCPToolRegistry
# ─────────────────────────────────────────────────────────────────────────────
 
class MCPToolRegistry:
    """
    Indexes every MCPAgentTool and stores the LIVE started client reference.
 
    The started client (from cl.start()) keeps its session open for the
    lifetime of the object. We call call_tool_sync() on THAT client — not
    on the MCPAgentTool's internal client (which may be a different ref).
 
    Entry shape:
    {
        "name":           str,
        "description":    str,
        "input_schema":   dict,
        "server_name":    str,
        "started_client": Any,    # ← the live client from cl.start()
    }
    """
 
    def __init__(self):
        self._tools: list[dict] = []
        self._index: dict[str, dict] = {}
 
    def register(self, server_name: str, started_client: Any, mcp_tools: list) -> int:
        """
        Index all tools from one server.
 
        Parameters
        ----------
        server_name    : human-readable name
        started_client : the object returned by MCPClient.start() — has
                         call_tool_sync() and the live session
        mcp_tools      : list[MCPAgentTool] from started_client.list_tools_sync()
        """
        count = 0
        for mcp_tool in mcp_tools:
            name      = mcp_tool.tool_name
            tool_spec = mcp_tool.tool_spec
 
            description  = tool_spec.get("description", "")
            raw_schema   = tool_spec.get("inputSchema", {})
            input_schema = raw_schema.get("json", raw_schema)  # unwrap {"json":{...}}
 
            entry = {
                "name":           server_name.lower() + "_" + name,
                "description":    description,
                "input_schema":   input_schema,
                "server_name":    server_name,
                "started_client": started_client,   # ← live session reference
            }
            self._tools.append(entry)
            self._index[name] = entry
            count += 1
        return count
 
    # ── search ────────────────────────────────────────────────────────────
 
    def search(self, query: str, top_k: int = 5) -> list[dict]:
        """Keyword search over name + description. No external deps needed."""
        words = set(re.findall(r"\w+", query.lower()))
        if not words:
            return self._tools[:top_k]
 
        scored: list[tuple[float, dict]] = []
        for entry in self._tools:
            text  = f"{entry['name']} {entry['description']}".lower()
            found = words & set(re.findall(r"\w+", text))
            score = len(found) / len(words)
            if score > 0:
                scored.append((score, entry))
 
        scored.sort(key=lambda x: x[0], reverse=True)
        return [e for _, e in scored[:top_k]]
 
    def get(self, name: str) -> dict | None:
        return self._index.get(name)
 
    @property
    def total(self) -> int:
        return len(self._tools)
 
    @property
    def all_tools(self) -> list[dict]:
        return self._tools
 
    def servers(self) -> list[str]:
        seen: list[str] = []
        for e in self._tools:
            if e["server_name"] not in seen:
                seen.append(e["server_name"])
        return seen
 
    def summary_for_prompt(self) -> str:
        by_server: dict[str, list[str]] = {}
        for e in self._tools:
            by_server.setdefault(e["server_name"], []).append(
                f"  • {e['name']}: {e['description'][:100]}"
            )
        lines = ["## Connected MCP Servers\n"]
        for server, tool_lines in by_server.items():
            lines.append(f"### {server}  ({len(tool_lines)} tools)")
            lines.extend(tool_lines)
            lines.append("")
        lines += [
            "Use `find_tool` to discover exact tool names and input schemas.",
            "Use `call_tool` to execute a tool once you know its exact name.",
        ]
        return "\n".join(lines)
 
    def debug(self):
        print(f"\n{'='*60}")
        print("MCP Optimizer Registry — Debug Info")
        print(f"{'='*60}")
        print(f"Total tools indexed : {self.total}")
        print(f"Servers             : {self.servers()}")
        print("\nAll indexed tools:")
        for e in self._tools:
            print(f"  [{e['server_name']}] {e['name']}")
            print(f"    {e['description'][:80]}")
        print(f"{'='*60}\n")
 
 
# ─────────────────────────────────────────────────────────────────────────────
# 2.  Tool factory — closures over a fully-populated, concrete registry
# ─────────────────────────────────────────────────────────────────────────────
 
def _make_tools(registry: MCPToolRegistry):
    """
    Build find_tool and call_tool as closures over a specific registry.
    Created AFTER the registry is populated — no global state, no timing bugs.
    """
 
    @strands_tool
    def find_tool(query: str, top_k: int = 5) -> str:
        """Search for MCP tools relevant to the current task.
 
        ALWAYS call this before call_tool when you need to use an external
        system or are unsure which tool to use. Returns matching tool names,
        descriptions, and input schemas so you know exactly what arguments
        to pass to call_tool.
 
        Args:
            query: Natural language description of what you want to do.
                   Examples: "get jira issue", "list github PRs", "send slack message"
            top_k: Maximum number of results to return. Default is 5.
 
        Returns:
            Formatted list of matching tools with names, descriptions, schemas.
        """
        query = query.strip()
        if not query:
            return "ERROR: query cannot be empty."
 
        results = registry.search(query, top_k=int(top_k))
 
        if not results:
            servers = ", ".join(registry.servers()) or "none"
            return (
                f"No tools found matching '{query}'.\n"
                f"Available servers: {servers}\n"
                "Try a broader search term."
            )
 
        lines = [f"Found {len(results)} tool(s) matching '{query}':\n"]
        for i, entry in enumerate(results, 1):
            schema_str = json.dumps(entry["input_schema"], indent=2)
            lines.append(
                f"[{i}] {entry['name']}  (server: {entry['server_name']})\n"
                f"    Description : {entry['description']}\n"
                f"    Input schema:\n{schema_str}\n"
            )
        return "\n".join(lines)
 
    @strands_tool
    def call_tool(tool_name: str, arguments: str) -> str:
        """Execute a specific MCP tool by its exact name.
 
        Always call find_tool first to get the exact tool name and input schema.
        Then call this with the tool name and a JSON string of arguments.
 
        Args:
            tool_name: Exact tool name as returned by find_tool.
                       Example: "jira_get_issue"
            arguments: Tool arguments as a valid JSON string matching the schema.
                       Example: '{"issue_key": "RBTES-121"}'
                       Use '{}' for tools that take no arguments.
 
        Returns:
            The tool output as a string.
        """
        tool_name = tool_name.strip()
        if not tool_name:
            return "ERROR: tool_name is required. Use find_tool to discover tool names."
 
        # ── Parse arguments ───────────────────────────────────────────────
        if isinstance(arguments, dict):
            args: dict = arguments
        else:
            args_str = (arguments or "{}").strip()
            try:
                args = json.loads(args_str)
            except json.JSONDecodeError as exc:
                return (
                    f"ERROR: arguments must be a valid JSON string.\n"
                    f"Received: {args_str!r}\n"
                    f"JSON error: {exc}\n"
                    f'Example: \'{{"issue_key": "RBTES-121"}}\''
                )
 
        # ── Look up tool ──────────────────────────────────────────────────
        entry = registry.get(tool_name)
        if entry is None:
            similar = registry.search(tool_name, top_k=3)
            suggestions = ", ".join(e["name"] for e in similar) if similar else "none found"
            return (
                f"ERROR: Tool '{tool_name}' not found in registry.\n"
                f"Did you mean: {suggestions}?\n"
                "Use find_tool to search for the correct tool name."
            )
 
        # ── Invoke via the live started_client ────────────────────────────
        # We use the started_client (from cl.start()) directly — this is the
        # same object whose session stays alive after your startup code runs.
        # This is exactly how your working direct-attachment code works.
        #
        # call_tool_sync signature (from mcp_client.py):
        #   call_tool_sync(tool_use_id: str, name: str, arguments: dict) -> dict
        #
        # Result shape: {"toolUseId": ..., "status": ..., "content": [{"text": ...}]}
        client = entry["started_client"]
        tool_use_id = f"optimizer-{uuid.uuid4().hex[:8]}"
 
        try:
            result = client.call_tool_sync(
                tool_use_id=tool_use_id,
                name=tool_name,
                arguments=args,
            )
        except Exception as exc:
            return (
                f"ERROR calling '{tool_name}': {type(exc).__name__}: {exc}\n"
                f"The MCP session for this tool may have closed. "
                f"Try restarting the agent."
            )
 
        # ── Extract text from result ──────────────────────────────────────
        if isinstance(result, dict):
            status         = result.get("status", "success")
            content_blocks = result.get("content", [])
 
            text_parts: list[str] = []
            for block in content_blocks:
                if isinstance(block, dict):
                    text = block.get("text", "")
                else:
                    text = getattr(block, "text", "")
                if text:
                    text_parts.append(str(text))
 
            output = "\n".join(text_parts) if text_parts else str(result)
 
            if status == "error":
                return f"Tool '{tool_name}' returned an error:\n{output}"
            return output or "(Tool returned an empty result)"
 
        # Fallback for unexpected result shapes
        return str(result) if result else "(Tool returned an empty result)"
 
    return find_tool, call_tool
