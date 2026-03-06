"""
Agentic chatbot built with the OpenAI Agents SDK.

The agent connects to the GitHub MCP server via stdio transport.
It auto-discovers all tools — no manual function imports needed.
Long-term memory is powered by Mem0 + Qdrant.
"""

import os
import sys
import asyncio
import logging
from agents import Agent, Runner
from agents.mcp import MCPServerStdio
from chat.long_memory import search_memory, add_memory

logger = logging.getLogger(__name__)

# Retry config for rate-limit errors
MAX_RETRIES = 3
BASE_RETRY_DELAY = 6  # seconds


# ── MCP Server config ───────────────────────────────────────────────────────
# Path to the MCP server scripts
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

MCP_SERVER_PATH = os.path.join(_BASE_DIR, "github_mcp", "mcp_github.py")
DOCKER_MCP_SERVER_PATH = os.path.join(_BASE_DIR, "docker_mcp", "mcp_docker.py")

# Python executable (use the same venv python that's running this process)
PYTHON_EXE = sys.executable


# ── Agent definition ─────────────────────────────────────────────────────────

SYSTEM_PROMPT = """\
You are a helpful DevOps assistant with full GitHub and Docker Hub capabilities.
You have tools for ALL GitHub operations (repos, branches, files, PRs, issues,
commits, releases, labels, collaborators, gists, workflows, orgs, webhooks,
user profile, notifications, deploy keys, deployments, packages, codespaces,
projects, security advisories, rate limits) and ALL Docker Hub operations
(repos, tags/images, access tokens, search, user profile).
Use the appropriate tool when the user asks you to do something.

Guidelines:
- When the user asks you to do something, use the appropriate tool.
- If a task requires multiple steps (e.g. create a repo → create a branch → push a file),
  execute them in sequence automatically.
- Always confirm what you did after completing the action.
- If you need information the user hasn't provided (like owner name), ask for it.
- Return concise, clear summaries of results.

--- CI/CD: Push GitHub Code to Docker Hub ---

When the user asks to "push code to Docker Hub", "deploy to Docker Hub",
"dockerize this repo", or similar, follow this EXACT multi-step workflow:

**Step 1 — Inspect the repository**
  - Use `list_directory_contents` to see the root of the repo.
  - Use `get_repo_languages` to detect the primary language/framework.
  - Check if a `Dockerfile` already exists (look in directory listing).
  - Check if `.github/workflows/` directory already exists.

**Step 2 — Generate a Dockerfile (if missing)**
  Based on the detected language, generate an appropriate Dockerfile:

  • **Node.js / Next.js** → multi-stage build with node:alpine, npm ci, build, then
    minimal runner stage.
  • **Python / FastAPI / Flask** → python:slim, COPY requirements.txt, pip install,
    COPY app, CMD.
  • **Go** → multi-stage with golang:alpine for build, scratch/distroless for run.
  • **Java / Spring Boot** → multi-stage with maven/gradle build, then eclipse-temurin
    JRE runner.
  • **Generic** → Ask the user about their stack and provide a best-effort Dockerfile.

  Push the Dockerfile using `push_file` to the repo's default branch (or a new
  branch if the user prefers).

**Step 3 — Create a GitHub Actions workflow**
  Push `.github/workflows/docker-publish.yml` using `push_file` with the
  following template (adjust image name and context as needed):

  ```yaml
  name: Build & Push to Docker Hub

  on:
    push:
      branches: [ "main" ]
    workflow_dispatch:

  jobs:
    build-and-push:
      runs-on: ubuntu-latest
      steps:
        - name: Checkout code
          uses: actions/checkout@v4

        - name: Set up Docker Buildx
          uses: docker/setup-buildx-action@v3

        - name: Log in to Docker Hub
          uses: docker/login-action@v3
          with:
            username: ${{ secrets.DOCKERHUB_USERNAME }}
            password: ${{ secrets.DOCKERHUB_TOKEN }}

        - name: Build and push
          uses: docker/build-push-action@v6
          with:
            context: .
            push: true
            tags: |
              ${{ secrets.DOCKERHUB_USERNAME }}/<IMAGE_NAME>:latest
              ${{ secrets.DOCKERHUB_USERNAME }}/<IMAGE_NAME>:${{ github.sha }}
            cache-from: type=gha
            cache-to: type=gha,mode=max
  ```

  Replace `<IMAGE_NAME>` with the repository name (lowercase).
  Adjust `context: .` if the Dockerfile is in a subdirectory.

**Step 4 — List required secrets**
  After pushing both files, ALWAYS tell the user exactly what GitHub repository
  secrets they need to set. Present it clearly like this:

  🔐 **GitHub Secrets required** (Settings → Secrets and variables → Actions):

  | Secret Name           | Value                                       |
  |-----------------------|---------------------------------------------|
  | `DOCKERHUB_USERNAME`  | Your Docker Hub username                    |
  | `DOCKERHUB_TOKEN`     | Your Docker Hub Personal Access Token (PAT) |

  Also mention:
  - They can create a Docker Hub PAT at https://hub.docker.com/settings/security
  - The PAT needs at least `Read & Write` scope.
  - The workflow triggers on pushes to `main` and can also be triggered manually
    via the "Run workflow" button in GitHub Actions.

**Step 5 — Confirm everything**
  Summarize what was done:
  - ✅ Dockerfile created (or already existed)
  - ✅ GitHub Actions workflow created at `.github/workflows/docker-publish.yml`
  - 🔐 Secrets to configure: `DOCKERHUB_USERNAME`, `DOCKERHUB_TOKEN`
  - 🚀 Next push to `main` will auto-build and push the Docker image

  If user's Docker Hub credentials are connected (check `user_context`),
  mention that the image will be pushed to `<docker_username>/<repo_name>`.

IMPORTANT: Do NOT skip steps. Always inspect the repo first. Always list the
required secrets. If the Dockerfile already exists, tell the user and skip to
the workflow step. If the workflow already exists, tell the user and ask if they
want to overwrite it.
"""


async def run_agent(
    user_message: str,
    conversation_history: list | None = None,
    github_token: str | None = None,
    docker_username: str | None = None,
    docker_pat: str | None = None,
    user_context: dict | None = None,
    user_id: str | None = None,
) -> str:
    """
    Run the DevOps agent with a user message.

    Spins up the GitHub + Docker Hub MCP servers as subprocesses via stdio,
    the agent auto-discovers all registered tools from them.
    Uses Mem0 for long-term memory (search before, save after).

    Args:
        user_message: The user's natural language message.
        conversation_history: Optional prior conversation turns for context.
        github_token: Optional per-user GitHub token (overrides .env default).
        docker_username: Optional Docker Hub username.
        docker_pat: Optional Docker Hub personal access token.
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
            f"- Docker Hub connected: {'Yes (user: ' + user_context.get('docker_username', '') + ')' if user_context.get('has_docker_token') else 'No — tell user to add Docker credentials on the website dashboard'}\n"
            f"- Phone: {user_context.get('phone') or 'not set'}\n"
            f"- Messages sent: {user_context.get('message_count', 0)}\n"
            f"\nIMPORTANT: When the user asks about their GitHub or Docker Hub connection status, "
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

    # Build env for the MCP subprocesses — inherit current env + override tokens
    mcp_env = dict(os.environ)
    if github_token:
        mcp_env["GITHUB_TOKEN"] = github_token

    docker_env = dict(os.environ)
    if docker_username:
        docker_env["DOCKER_USERNAME"] = docker_username
    if docker_pat:
        docker_env["DOCKER_PAT"] = docker_pat

    # Connect to both MCP servers via stdio — agent auto-discovers all tools
    async with MCPServerStdio(
        name="GitHub MCP Server",
        params={
            "command": PYTHON_EXE,
            "args": [MCP_SERVER_PATH],
            "env": mcp_env,
        },
    ) as github_mcp, MCPServerStdio(
        name="Docker Hub MCP Server",
        params={
            "command": PYTHON_EXE,
            "args": [DOCKER_MCP_SERVER_PATH],
            "env": docker_env,
        },
    ) as docker_mcp:
        agent = Agent(
            name="DevOps Assistant",
            instructions=prompt,
            mcp_servers=[github_mcp, docker_mcp],
        )

        # Retry with exponential backoff on rate-limit (429) errors
        last_err = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                result = await Runner.run(agent, input=input_messages)
                reply = result.final_output
                break
            except Exception as e:
                err_str = str(e)
                if "429" in err_str or "rate_limit" in err_str.lower():
                    wait = BASE_RETRY_DELAY * attempt
                    logger.warning(f"Rate limited (attempt {attempt}/{MAX_RETRIES}), retrying in {wait}s...")
                    last_err = e
                    await asyncio.sleep(wait)
                else:
                    raise
        else:
            # All retries exhausted
            raise last_err  # type: ignore[misc]

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
