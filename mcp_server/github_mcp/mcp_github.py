"""
MCP GitHub Server — a proper MCP server exposing GitHub operations as tools.

Run standalone:
    python mcp/mcp_github.py

The OpenAI Agent SDK connects to this via MCPServerStdio.
"""

import os
import json
import base64
import asyncio
import httpx
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

load_dotenv()

GITHUB_API = "https://api.github.com"
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")

mcp_server = FastMCP("GitHub MCP Server")


def _headers() -> dict:
    """Common headers for every GitHub API call."""
    return {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


# ── 1. Create Repository ────────────────────────────────────────────────────

@mcp_server.tool()
async def create_repository(
    name: str,
    description: str = "",
    private: bool = False,
    auto_init: bool = True,
) -> str:
    """Create a new GitHub repository for the authenticated user.

    Args:
        name: Repository name (e.g. 'my-awesome-project').
        description: Short description of the repo.
        private: True for a private repo, False for public.
        auto_init: Whether to add a README on creation.
    """
    payload = {
        "name": name,
        "description": description,
        "private": private,
        "auto_init": auto_init,
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{GITHUB_API}/user/repos",
            headers=_headers(),
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
    return json.dumps({
        "repo": data.get("full_name"),
        "url": data.get("html_url"),
        "private": data.get("private"),
        "description": data.get("description"),
    })


# ── 2. Get Repository Details ────────────────────────────────────────────────

@mcp_server.tool()
async def get_repository(owner: str, repo: str) -> str:
    """Get full details of a GitHub repository.

    Args:
        owner: Repository owner (username or org).
        repo: Repository name.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{GITHUB_API}/repos/{owner}/{repo}",
            headers=_headers(),
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
    return json.dumps({
        "full_name": data.get("full_name"),
        "url": data.get("html_url"),
        "description": data.get("description"),
        "private": data.get("private"),
        "stars": data.get("stargazers_count"),
        "forks": data.get("forks_count"),
        "open_issues": data.get("open_issues_count"),
        "default_branch": data.get("default_branch"),
        "language": data.get("language"),
        "created_at": data.get("created_at"),
        "updated_at": data.get("updated_at"),
    })


# ── 3. List Repositories ────────────────────────────────────────────────────

@mcp_server.tool()
async def list_repositories(per_page: int = 30, page: int = 1) -> str:
    """List repositories for the authenticated GitHub user.

    Args:
        per_page: Number of repos per page (max 100).
        page: Page number.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{GITHUB_API}/user/repos",
            headers=_headers(),
            params={"per_page": per_page, "page": page, "sort": "updated"},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
    repos = [
        {
            "name": r.get("full_name"),
            "url": r.get("html_url"),
            "private": r.get("private"),
            "language": r.get("language"),
        }
        for r in data
    ]
    return json.dumps(repos)


# ── 4. Create Branch ────────────────────────────────────────────────────────

@mcp_server.tool()
async def create_branch(
    owner: str,
    repo: str,
    branch_name: str,
    from_branch: str = "main",
) -> str:
    """Create a new branch in a GitHub repository.

    Args:
        owner: Repository owner.
        repo: Repository name.
        branch_name: Name for the new branch.
        from_branch: Source branch to branch from (default: main).
    """
    async with httpx.AsyncClient() as client:
        # Get SHA of the source branch
        ref_resp = await client.get(
            f"{GITHUB_API}/repos/{owner}/{repo}/git/ref/heads/{from_branch}",
            headers=_headers(),
            timeout=30,
        )
        ref_resp.raise_for_status()
        sha = ref_resp.json()["object"]["sha"]

        # Create new ref
        create_resp = await client.post(
            f"{GITHUB_API}/repos/{owner}/{repo}/git/refs",
            headers=_headers(),
            json={"ref": f"refs/heads/{branch_name}", "sha": sha},
            timeout=30,
        )
        create_resp.raise_for_status()
        data = create_resp.json()
    return json.dumps({
        "ref": data.get("ref"),
        "sha": data.get("object", {}).get("sha"),
    })


# ── 5. Push File (create / update) ──────────────────────────────────────────

@mcp_server.tool()
async def push_file(
    owner: str,
    repo: str,
    branch: str,
    file_path: str,
    content: str,
    commit_message: str = "Add file via API",
) -> str:
    """Create or update a single file on a branch in a GitHub repository.

    Args:
        owner: Repository owner.
        repo: Repository name.
        branch: Branch to push to.
        file_path: Path of the file inside the repo (e.g. src/app.py).
        content: Raw text content of the file.
        commit_message: Commit message for the change.
    """
    encoded = base64.b64encode(content.encode()).decode()

    async with httpx.AsyncClient() as client:
        # Check if file already exists (to get its SHA for updates)
        sha = None
        existing = await client.get(
            f"{GITHUB_API}/repos/{owner}/{repo}/contents/{file_path}",
            headers=_headers(),
            params={"ref": branch},
            timeout=30,
        )
        if existing.status_code == 200:
            sha = existing.json()["sha"]

        payload: dict = {
            "message": commit_message,
            "content": encoded,
            "branch": branch,
        }
        if sha:
            payload["sha"] = sha

        resp = await client.put(
            f"{GITHUB_API}/repos/{owner}/{repo}/contents/{file_path}",
            headers=_headers(),
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
    return json.dumps({
        "file": data.get("content", {}).get("path"),
        "sha": data.get("content", {}).get("sha"),
        "commit_sha": data.get("commit", {}).get("sha"),
        "commit_message": data.get("commit", {}).get("message"),
    })


# ── 6. Merge Branches ───────────────────────────────────────────────────────

@mcp_server.tool()
async def merge_branches(
    owner: str,
    repo: str,
    base: str,
    head: str,
    commit_message: str = "Merge branch",
) -> str:
    """Merge one branch into another in a GitHub repository.

    Args:
        owner: Repository owner.
        repo: Repository name.
        base: Branch to merge INTO (target).
        head: Branch to merge FROM (source).
        commit_message: Message for the merge commit.
    """
    payload = {
        "base": base,
        "head": head,
        "commit_message": commit_message,
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{GITHUB_API}/repos/{owner}/{repo}/merges",
            headers=_headers(),
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
    return json.dumps({
        "sha": data.get("sha"),
        "message": data.get("commit", {}).get("message"),
    })


# ── 7. List Branches ────────────────────────────────────────────────────────

@mcp_server.tool()
async def list_branches(owner: str, repo: str) -> str:
    """List all branches of a GitHub repository.

    Args:
        owner: Repository owner.
        repo: Repository name.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{GITHUB_API}/repos/{owner}/{repo}/branches",
            headers=_headers(),
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
    branches = [
        {
            "name": b.get("name"),
            "sha": b.get("commit", {}).get("sha"),
            "protected": b.get("protected"),
        }
        for b in data
    ]
    return json.dumps(branches)


# ── 8. Create Pull Request ──────────────────────────────────────────────────

@mcp_server.tool()
async def create_pull_request(
    owner: str,
    repo: str,
    title: str,
    head: str,
    base: str = "main",
    body: str = "",
) -> str:
    """Create a pull request in a GitHub repository.

    Args:
        owner: Repository owner.
        repo: Repository name.
        title: Title of the pull request.
        head: Source branch (the one with changes).
        base: Target branch to merge into (default: main).
        body: Description / body of the PR.
    """
    payload = {
        "title": title,
        "head": head,
        "base": base,
        "body": body,
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{GITHUB_API}/repos/{owner}/{repo}/pulls",
            headers=_headers(),
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
    return json.dumps({
        "pr_number": data.get("number"),
        "url": data.get("html_url"),
        "title": data.get("title"),
        "state": data.get("state"),
    })


# ── Run the MCP server via stdio ─────────────────────────────────────────────

if __name__ == "__main__":
    mcp_server.run(transport="stdio")
