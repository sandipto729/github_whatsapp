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

**Repositories:**
- Create, update, delete repositories (public/private, with README)
- Get repository details, list repos, list contributors, list stargazers
- Get repository languages, list/update topics, get README
- Fork repositories, list forks, list directory contents
- Compare commits between branches/tags, archive repos

**Branches & Tags:**
- Create, list, delete branches
- Merge branches
- Create, list, delete tags

**Files:**
- Push/create/update files on a branch
- Get file contents, delete files, list directory contents

**Pull Requests:**
- Create, list, get, update, merge pull requests (merge/squash/rebase)
- List PR files, add PR reviews (approve/request changes/comment)

**Issues:**
- Create, list, get, update issues
- Add comments, list comments on issues
- Filter by state, labels, assignees

**Commits & Status:**
- List commits, get commit details
- Get combined commit status, create commit statuses
- List check runs for a ref

**Search:**
- Search repositories, code, issues/PRs, users across all of GitHub

**Releases:**
- Create, list, delete releases (with drafts, pre-releases)

**Labels & Milestones:**
- Create, list, delete labels
- Create, list milestones

**Collaborators & Invitations:**
- Add, remove, list repository collaborators
- List pending repository invitations

**Gists:**
- Create, list, get, delete gists (public/secret)

**GitHub Actions & Workflows:**
- List workflows, trigger workflow dispatch
- List workflow runs, cancel runs, re-run workflows

**Organizations & Teams:**
- List organizations, list org members, list org repos
- List teams, list team members

**Webhooks:**
- Create, list, delete repository webhooks

**User & Profile:**
- Get authenticated user profile, get any user profile
- List/add SSH keys, list/add GPG keys
- List user emails
- Star/unstar repos, list starred repos
- Follow/unfollow users, list followers/following

**Notifications:**
- List notifications, mark all as read

**Deploy Keys:**
- List, add, delete deploy keys

**Deployments & Environments:**
- List deployments, create deployment statuses
- List deployment environments

**Packages:**
- List, delete packages (npm, docker, nuget, etc.)

**Codespaces:**
- List codespaces

**Projects:**
- List repository projects (classic)

**Security:**
- List security advisories

**Monitoring:**
- Get API rate limit status

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
