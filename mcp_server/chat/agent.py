"""
Agentic chatbot built with the OpenAI Agents SDK.

The agent connects to the GitHub MCP server via stdio transport.
It auto-discovers all tools — no manual function imports needed.
Long-term memory is powered by Mem0 + Qdrant.
"""

import os
import sys
from agents import Agent, Runner
from agents.mcp import MCPServerStdio
from chat.long_memory import search_memory, add_memory


# ── MCP Server config ───────────────────────────────────────────────────────
# Path to the MCP server script
MCP_SERVER_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "github_mcp",
    "mcp_github.py",
)

# Python executable (use the same venv python that's running this process)
PYTHON_EXE = sys.executable


# ── Agent definition ─────────────────────────────────────────────────────────

SYSTEM_PROMPT = """\
You are a helpful GitHub assistant. You can perform GitHub operations for the user
using the tools available to you.

Capabilities:
- Create repositories (public / private, with README, with description)
- Get repository details
- List the user's repositories
- Create branches
- Push / update files on a branch
- Merge branches
- List branches
- Create pull requests

Guidelines:
- When the user asks you to do something, use the appropriate tool.
- If a task requires multiple steps (e.g. create a repo → create a branch → push a file),
  execute them in sequence automatically.
- Always confirm what you did after completing the action.
- If you need information the user hasn't provided (like owner name), ask for it.
- Return concise, clear summaries of results.
"""


async def run_agent(
    user_message: str,
    conversation_history: list | None = None,
    github_token: str | None = None,
    user_context: dict | None = None,
    user_id: str | None = None,
) -> str:
    """
    Run the GitHub agent with a user message.

    Spins up the MCP server as a subprocess via stdio, the agent
    auto-discovers all registered tools from it.
    Uses Mem0 for long-term memory (search before, save after).

    Args:
        user_message: The user's natural language message.
        conversation_history: Optional prior conversation turns for context.
        github_token: Optional per-user GitHub token (overrides .env default).
        user_context: Optional dict with user profile info.
        user_id: Optional MongoDB _id string for long-term memory.

    Returns:
        The agent's text response.
    """
    # Map common role aliases to OpenAI-accepted roles
    ROLE_MAP = {
        "human": "user",
        "bot": "assistant",
        "ai": "assistant",
        "system": "system",
        "developer": "developer",
        "user": "user",
        "assistant": "assistant",
    }

    # Build dynamic system prompt with user context
    prompt = SYSTEM_PROMPT
    if user_context:
        ctx = (
            f"\n\nCurrent user info:\n"
            f"- Username: {user_context.get('username', 'unknown')}\n"
            f"- GitHub token connected: {'Yes' if user_context.get('has_github_token') else 'No — tell user to add it on the website dashboard'}\n"
            f"- Phone: {user_context.get('phone') or 'not set'}\n"
            f"- Messages sent: {user_context.get('message_count', 0)}\n"
            f"\nIMPORTANT: When the user asks about their GitHub connection status, "
            f"answer based ONLY on the info above. Do NOT guess or hallucinate."
        )
        prompt += ctx

    # ── Long-term memory: search for relevant context ────────────────────
    if user_id:
        long_term_ctx = search_memory(user_id, user_message)
        if long_term_ctx:
            prompt += f"\n\n{long_term_ctx}\nUse these memories to give more personalised answers."

    # Build the input messages list
    input_messages = []
    if conversation_history:
        for turn in conversation_history:
            raw_role = turn.get("role", "user").lower()
            role = ROLE_MAP.get(raw_role, "user")
            input_messages.append({
                "role": role,
                "content": turn.get("content", ""),
            })
    input_messages.append({"role": "user", "content": user_message})

    # Build env for the MCP subprocess — inherit current env + override token if provided
    mcp_env = dict(os.environ)
    if github_token:
        mcp_env["GITHUB_TOKEN"] = github_token

    # Connect to MCP server via stdio — agent auto-discovers all tools
    async with MCPServerStdio(
        name="GitHub MCP Server",
        params={
            "command": PYTHON_EXE,
            "args": [MCP_SERVER_PATH],
            "env": mcp_env,
        },
    ) as mcp_server:
        agent = Agent(
            name="GitHub Assistant",
            instructions=prompt,
            mcp_servers=[mcp_server],
        )

        result = await Runner.run(agent, input=input_messages)
        reply = result.final_output

    # ── Long-term memory: save the exchange ──────────────────────────────
    if user_id:
        add_memory(
            user_id,
            [
                {"role": "user", "content": user_message},
                {"role": "assistant", "content": reply},
            ],
        )

    return reply
