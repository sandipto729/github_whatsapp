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


# ── 9. List Pull Requests ───────────────────────────────────────────────────

@mcp_server.tool()
async def list_pull_requests(
    owner: str,
    repo: str,
    state: str = "open",
    per_page: int = 30,
    page: int = 1,
) -> str:
    """List pull requests in a GitHub repository.

    Args:
        owner: Repository owner.
        repo: Repository name.
        state: Filter by state: open, closed, all.
        per_page: Results per page (max 100).
        page: Page number.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{GITHUB_API}/repos/{owner}/{repo}/pulls",
            headers=_headers(),
            params={"state": state, "per_page": per_page, "page": page},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
    return json.dumps([
        {
            "number": p.get("number"),
            "title": p.get("title"),
            "state": p.get("state"),
            "url": p.get("html_url"),
            "user": p.get("user", {}).get("login"),
            "head": p.get("head", {}).get("ref"),
            "base": p.get("base", {}).get("ref"),
            "created_at": p.get("created_at"),
        }
        for p in data
    ])


# ── 10. Get Pull Request ────────────────────────────────────────────────────

@mcp_server.tool()
async def get_pull_request(owner: str, repo: str, pull_number: int) -> str:
    """Get details of a specific pull request.

    Args:
        owner: Repository owner.
        repo: Repository name.
        pull_number: PR number.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{GITHUB_API}/repos/{owner}/{repo}/pulls/{pull_number}",
            headers=_headers(),
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
    return json.dumps({
        "number": data.get("number"),
        "title": data.get("title"),
        "state": data.get("state"),
        "url": data.get("html_url"),
        "body": data.get("body"),
        "user": data.get("user", {}).get("login"),
        "head": data.get("head", {}).get("ref"),
        "base": data.get("base", {}).get("ref"),
        "mergeable": data.get("mergeable"),
        "merged": data.get("merged"),
        "comments": data.get("comments"),
        "commits": data.get("commits"),
        "additions": data.get("additions"),
        "deletions": data.get("deletions"),
        "changed_files": data.get("changed_files"),
        "created_at": data.get("created_at"),
        "updated_at": data.get("updated_at"),
    })


# ── 11. Merge Pull Request ──────────────────────────────────────────────────

@mcp_server.tool()
async def merge_pull_request(
    owner: str,
    repo: str,
    pull_number: int,
    merge_method: str = "merge",
    commit_title: str = "",
    commit_message: str = "",
) -> str:
    """Merge a pull request.

    Args:
        owner: Repository owner.
        repo: Repository name.
        pull_number: PR number.
        merge_method: Merge method: merge, squash, or rebase.
        commit_title: Custom title for the merge commit.
        commit_message: Custom message for the merge commit.
    """
    payload: dict = {"merge_method": merge_method}
    if commit_title:
        payload["commit_title"] = commit_title
    if commit_message:
        payload["commit_message"] = commit_message
    async with httpx.AsyncClient() as client:
        resp = await client.put(
            f"{GITHUB_API}/repos/{owner}/{repo}/pulls/{pull_number}/merge",
            headers=_headers(),
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
    return json.dumps({
        "merged": data.get("merged"),
        "message": data.get("message"),
        "sha": data.get("sha"),
    })


# ── 12. Update Pull Request ─────────────────────────────────────────────────

@mcp_server.tool()
async def update_pull_request(
    owner: str,
    repo: str,
    pull_number: int,
    title: str = "",
    body: str = "",
    state: str = "",
) -> str:
    """Update a pull request (title, body, or state).

    Args:
        owner: Repository owner.
        repo: Repository name.
        pull_number: PR number to update.
        title: New title (leave empty to keep current).
        body: New body/description (leave empty to keep current).
        state: New state: open or closed (leave empty to keep current).
    """
    payload: dict = {}
    if title:
        payload["title"] = title
    if body:
        payload["body"] = body
    if state:
        payload["state"] = state
    async with httpx.AsyncClient() as client:
        resp = await client.patch(
            f"{GITHUB_API}/repos/{owner}/{repo}/pulls/{pull_number}",
            headers=_headers(),
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
    return json.dumps({
        "number": data.get("number"),
        "title": data.get("title"),
        "state": data.get("state"),
        "url": data.get("html_url"),
    })


# ── 13. List PR Files ───────────────────────────────────────────────────────

@mcp_server.tool()
async def list_pull_request_files(
    owner: str, repo: str, pull_number: int,
) -> str:
    """List files changed in a pull request.

    Args:
        owner: Repository owner.
        repo: Repository name.
        pull_number: PR number.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{GITHUB_API}/repos/{owner}/{repo}/pulls/{pull_number}/files",
            headers=_headers(),
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
    return json.dumps([
        {
            "filename": f.get("filename"),
            "status": f.get("status"),
            "additions": f.get("additions"),
            "deletions": f.get("deletions"),
            "changes": f.get("changes"),
        }
        for f in data
    ])


# ── 14. Add PR Review ───────────────────────────────────────────────────────

@mcp_server.tool()
async def create_pull_request_review(
    owner: str,
    repo: str,
    pull_number: int,
    body: str = "",
    event: str = "COMMENT",
) -> str:
    """Submit a review on a pull request.

    Args:
        owner: Repository owner.
        repo: Repository name.
        pull_number: PR number.
        body: Review comment body.
        event: Review action: APPROVE, REQUEST_CHANGES, or COMMENT.
    """
    payload: dict = {"event": event}
    if body:
        payload["body"] = body
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{GITHUB_API}/repos/{owner}/{repo}/pulls/{pull_number}/reviews",
            headers=_headers(),
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
    return json.dumps({
        "id": data.get("id"),
        "state": data.get("state"),
        "body": data.get("body"),
        "user": data.get("user", {}).get("login"),
    })


# ── 15. Create Issue ────────────────────────────────────────────────────────

@mcp_server.tool()
async def create_issue(
    owner: str,
    repo: str,
    title: str,
    body: str = "",
    labels: str = "",
    assignees: str = "",
) -> str:
    """Create a new issue in a GitHub repository.

    Args:
        owner: Repository owner.
        repo: Repository name.
        title: Issue title.
        body: Issue body/description.
        labels: Comma-separated label names (e.g. 'bug,enhancement').
        assignees: Comma-separated usernames to assign.
    """
    payload: dict = {"title": title, "body": body}
    if labels:
        payload["labels"] = [l.strip() for l in labels.split(",")]
    if assignees:
        payload["assignees"] = [a.strip() for a in assignees.split(",")]
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{GITHUB_API}/repos/{owner}/{repo}/issues",
            headers=_headers(),
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
    return json.dumps({
        "number": data.get("number"),
        "title": data.get("title"),
        "url": data.get("html_url"),
        "state": data.get("state"),
    })


# ── 16. List Issues ─────────────────────────────────────────────────────────

@mcp_server.tool()
async def list_issues(
    owner: str,
    repo: str,
    state: str = "open",
    labels: str = "",
    per_page: int = 30,
    page: int = 1,
) -> str:
    """List issues in a GitHub repository.

    Args:
        owner: Repository owner.
        repo: Repository name.
        state: Filter by state: open, closed, all.
        labels: Comma-separated label names to filter by.
        per_page: Results per page (max 100).
        page: Page number.
    """
    params: dict = {"state": state, "per_page": per_page, "page": page}
    if labels:
        params["labels"] = labels
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{GITHUB_API}/repos/{owner}/{repo}/issues",
            headers=_headers(),
            params=params,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
    return json.dumps([
        {
            "number": i.get("number"),
            "title": i.get("title"),
            "state": i.get("state"),
            "url": i.get("html_url"),
            "user": i.get("user", {}).get("login"),
            "labels": [l.get("name") for l in i.get("labels", [])],
            "created_at": i.get("created_at"),
        }
        for i in data
    ])


# ── 17. Get Issue ───────────────────────────────────────────────────────────

@mcp_server.tool()
async def get_issue(owner: str, repo: str, issue_number: int) -> str:
    """Get details of a specific issue.

    Args:
        owner: Repository owner.
        repo: Repository name.
        issue_number: Issue number.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{GITHUB_API}/repos/{owner}/{repo}/issues/{issue_number}",
            headers=_headers(),
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
    return json.dumps({
        "number": data.get("number"),
        "title": data.get("title"),
        "state": data.get("state"),
        "url": data.get("html_url"),
        "body": data.get("body"),
        "user": data.get("user", {}).get("login"),
        "labels": [l.get("name") for l in data.get("labels", [])],
        "assignees": [a.get("login") for a in data.get("assignees", [])],
        "comments": data.get("comments"),
        "created_at": data.get("created_at"),
        "updated_at": data.get("updated_at"),
        "closed_at": data.get("closed_at"),
    })


# ── 18. Update Issue ────────────────────────────────────────────────────────

@mcp_server.tool()
async def update_issue(
    owner: str,
    repo: str,
    issue_number: int,
    title: str = "",
    body: str = "",
    state: str = "",
    labels: str = "",
    assignees: str = "",
) -> str:
    """Update an existing issue.

    Args:
        owner: Repository owner.
        repo: Repository name.
        issue_number: Issue number.
        title: New title (leave empty to keep current).
        body: New body (leave empty to keep current).
        state: New state: open or closed (leave empty to keep current).
        labels: Comma-separated label names to set (replaces existing).
        assignees: Comma-separated usernames to assign (replaces existing).
    """
    payload: dict = {}
    if title:
        payload["title"] = title
    if body:
        payload["body"] = body
    if state:
        payload["state"] = state
    if labels:
        payload["labels"] = [l.strip() for l in labels.split(",")]
    if assignees:
        payload["assignees"] = [a.strip() for a in assignees.split(",")]
    async with httpx.AsyncClient() as client:
        resp = await client.patch(
            f"{GITHUB_API}/repos/{owner}/{repo}/issues/{issue_number}",
            headers=_headers(),
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
    return json.dumps({
        "number": data.get("number"),
        "title": data.get("title"),
        "state": data.get("state"),
        "url": data.get("html_url"),
    })


# ── 19. Add Issue Comment ───────────────────────────────────────────────────

@mcp_server.tool()
async def add_issue_comment(
    owner: str, repo: str, issue_number: int, body: str,
) -> str:
    """Add a comment to an issue or pull request.

    Args:
        owner: Repository owner.
        repo: Repository name.
        issue_number: Issue or PR number.
        body: Comment body text.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{GITHUB_API}/repos/{owner}/{repo}/issues/{issue_number}/comments",
            headers=_headers(),
            json={"body": body},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
    return json.dumps({
        "id": data.get("id"),
        "url": data.get("html_url"),
        "body": data.get("body"),
        "user": data.get("user", {}).get("login"),
        "created_at": data.get("created_at"),
    })


# ── 20. List Issue Comments ─────────────────────────────────────────────────

@mcp_server.tool()
async def list_issue_comments(
    owner: str, repo: str, issue_number: int, per_page: int = 30, page: int = 1,
) -> str:
    """List comments on an issue or pull request.

    Args:
        owner: Repository owner.
        repo: Repository name.
        issue_number: Issue or PR number.
        per_page: Results per page (max 100).
        page: Page number.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{GITHUB_API}/repos/{owner}/{repo}/issues/{issue_number}/comments",
            headers=_headers(),
            params={"per_page": per_page, "page": page},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
    return json.dumps([
        {
            "id": c.get("id"),
            "body": c.get("body"),
            "user": c.get("user", {}).get("login"),
            "created_at": c.get("created_at"),
            "updated_at": c.get("updated_at"),
        }
        for c in data
    ])


# ── 21. List Commits ────────────────────────────────────────────────────────

@mcp_server.tool()
async def list_commits(
    owner: str,
    repo: str,
    branch: str = "",
    per_page: int = 30,
    page: int = 1,
) -> str:
    """List commits in a repository.

    Args:
        owner: Repository owner.
        repo: Repository name.
        branch: Branch name (SHA or ref). Defaults to the default branch.
        per_page: Results per page (max 100).
        page: Page number.
    """
    params: dict = {"per_page": per_page, "page": page}
    if branch:
        params["sha"] = branch
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{GITHUB_API}/repos/{owner}/{repo}/commits",
            headers=_headers(),
            params=params,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
    return json.dumps([
        {
            "sha": c.get("sha"),
            "message": c.get("commit", {}).get("message"),
            "author": c.get("commit", {}).get("author", {}).get("name"),
            "date": c.get("commit", {}).get("author", {}).get("date"),
            "url": c.get("html_url"),
        }
        for c in data
    ])


# ── 22. Get Commit ──────────────────────────────────────────────────────────

@mcp_server.tool()
async def get_commit(owner: str, repo: str, commit_sha: str) -> str:
    """Get details of a specific commit.

    Args:
        owner: Repository owner.
        repo: Repository name.
        commit_sha: The SHA of the commit.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{GITHUB_API}/repos/{owner}/{repo}/commits/{commit_sha}",
            headers=_headers(),
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
    return json.dumps({
        "sha": data.get("sha"),
        "message": data.get("commit", {}).get("message"),
        "author": data.get("commit", {}).get("author", {}).get("name"),
        "date": data.get("commit", {}).get("author", {}).get("date"),
        "url": data.get("html_url"),
        "stats": data.get("stats"),
        "files": [
            {
                "filename": f.get("filename"),
                "status": f.get("status"),
                "additions": f.get("additions"),
                "deletions": f.get("deletions"),
            }
            for f in data.get("files", [])
        ],
    })


# ── 23. Get Combined Commit Status ──────────────────────────────────────────

@mcp_server.tool()
async def get_commit_status(owner: str, repo: str, ref: str) -> str:
    """Get the combined status for a specific ref (branch, tag, or SHA).

    Args:
        owner: Repository owner.
        repo: Repository name.
        ref: Git ref (branch name, tag, or commit SHA).
    """
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{GITHUB_API}/repos/{owner}/{repo}/commits/{ref}/status",
            headers=_headers(),
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
    return json.dumps({
        "state": data.get("state"),
        "total_count": data.get("total_count"),
        "statuses": [
            {
                "state": s.get("state"),
                "context": s.get("context"),
                "description": s.get("description"),
                "target_url": s.get("target_url"),
            }
            for s in data.get("statuses", [])
        ],
    })


# ── 24. Create Commit Status ────────────────────────────────────────────────

@mcp_server.tool()
async def create_commit_status(
    owner: str,
    repo: str,
    sha: str,
    state: str,
    target_url: str = "",
    description: str = "",
    context: str = "default",
) -> str:
    """Create a commit status (for CI/CD integrations).

    Args:
        owner: Repository owner.
        repo: Repository name.
        sha: The commit SHA to set status on.
        state: Status state: error, failure, pending, or success.
        target_url: URL to associate with the status.
        description: Short description of the status.
        context: A label to differentiate this status from others (e.g. 'ci/build').
    """
    payload: dict = {"state": state, "context": context}
    if target_url:
        payload["target_url"] = target_url
    if description:
        payload["description"] = description
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{GITHUB_API}/repos/{owner}/{repo}/statuses/{sha}",
            headers=_headers(),
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
    return json.dumps({
        "id": data.get("id"),
        "state": data.get("state"),
        "context": data.get("context"),
        "description": data.get("description"),
        "target_url": data.get("target_url"),
        "created_at": data.get("created_at"),
    })


# ── 25. Search Repositories ─────────────────────────────────────────────────

@mcp_server.tool()
async def search_repositories(
    query: str, sort: str = "stars", order: str = "desc", per_page: int = 10,
) -> str:
    """Search GitHub repositories.

    Args:
        query: Search query (e.g. 'machine learning language:python').
        sort: Sort field: stars, forks, help-wanted-issues, updated.
        order: Sort order: asc or desc.
        per_page: Results per page (max 100).
    """
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{GITHUB_API}/search/repositories",
            headers=_headers(),
            params={"q": query, "sort": sort, "order": order, "per_page": per_page},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
    return json.dumps({
        "total_count": data.get("total_count"),
        "items": [
            {
                "full_name": r.get("full_name"),
                "url": r.get("html_url"),
                "description": r.get("description"),
                "stars": r.get("stargazers_count"),
                "forks": r.get("forks_count"),
                "language": r.get("language"),
            }
            for r in data.get("items", [])
        ],
    })


# ── 26. Search Code ─────────────────────────────────────────────────────────

@mcp_server.tool()
async def search_code(
    query: str, per_page: int = 10,
) -> str:
    """Search for code across GitHub repositories.

    Args:
        query: Search query (e.g. 'FastAPI repo:owner/repo' or 'class MyModel extension:py').
        per_page: Results per page (max 100).
    """
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{GITHUB_API}/search/code",
            headers=_headers(),
            params={"q": query, "per_page": per_page},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
    return json.dumps({
        "total_count": data.get("total_count"),
        "items": [
            {
                "name": r.get("name"),
                "path": r.get("path"),
                "repository": r.get("repository", {}).get("full_name"),
                "url": r.get("html_url"),
            }
            for r in data.get("items", [])
        ],
    })


# ── 27. Search Issues & PRs ─────────────────────────────────────────────────

@mcp_server.tool()
async def search_issues(
    query: str, sort: str = "created", order: str = "desc", per_page: int = 10,
) -> str:
    """Search issues and pull requests across GitHub.

    Args:
        query: Search query (e.g. 'bug label:bug repo:owner/repo is:open').
        sort: Sort field: comments, reactions, created, updated.
        order: Sort order: asc or desc.
        per_page: Results per page (max 100).
    """
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{GITHUB_API}/search/issues",
            headers=_headers(),
            params={"q": query, "sort": sort, "order": order, "per_page": per_page},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
    return json.dumps({
        "total_count": data.get("total_count"),
        "items": [
            {
                "number": r.get("number"),
                "title": r.get("title"),
                "state": r.get("state"),
                "url": r.get("html_url"),
                "user": r.get("user", {}).get("login"),
                "labels": [l.get("name") for l in r.get("labels", [])],
                "created_at": r.get("created_at"),
            }
            for r in data.get("items", [])
        ],
    })


# ── 28. Search Users ────────────────────────────────────────────────────────

@mcp_server.tool()
async def search_users(
    query: str, sort: str = "followers", order: str = "desc", per_page: int = 10,
) -> str:
    """Search GitHub users.

    Args:
        query: Search query (e.g. 'tom language:python location:USA').
        sort: Sort field: followers, repositories, joined.
        order: Sort order: asc or desc.
        per_page: Results per page (max 100).
    """
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{GITHUB_API}/search/users",
            headers=_headers(),
            params={"q": query, "sort": sort, "order": order, "per_page": per_page},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
    return json.dumps({
        "total_count": data.get("total_count"),
        "items": [
            {
                "login": u.get("login"),
                "url": u.get("html_url"),
                "avatar_url": u.get("avatar_url"),
                "type": u.get("type"),
            }
            for u in data.get("items", [])
        ],
    })


# ── 29. Get Authenticated User ──────────────────────────────────────────────

@mcp_server.tool()
async def get_authenticated_user() -> str:
    """Get the profile of the currently authenticated GitHub user."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{GITHUB_API}/user",
            headers=_headers(),
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
    return json.dumps({
        "login": data.get("login"),
        "name": data.get("name"),
        "email": data.get("email"),
        "bio": data.get("bio"),
        "url": data.get("html_url"),
        "public_repos": data.get("public_repos"),
        "public_gists": data.get("public_gists"),
        "followers": data.get("followers"),
        "following": data.get("following"),
        "created_at": data.get("created_at"),
    })


# ── 30. Get User Profile ────────────────────────────────────────────────────

@mcp_server.tool()
async def get_user_profile(username: str) -> str:
    """Get the public profile of any GitHub user.

    Args:
        username: GitHub username.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{GITHUB_API}/users/{username}",
            headers=_headers(),
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
    return json.dumps({
        "login": data.get("login"),
        "name": data.get("name"),
        "bio": data.get("bio"),
        "company": data.get("company"),
        "location": data.get("location"),
        "url": data.get("html_url"),
        "public_repos": data.get("public_repos"),
        "followers": data.get("followers"),
        "following": data.get("following"),
        "created_at": data.get("created_at"),
    })


# ── 31. Star Repository ─────────────────────────────────────────────────────

@mcp_server.tool()
async def star_repository(owner: str, repo: str) -> str:
    """Star a GitHub repository.

    Args:
        owner: Repository owner.
        repo: Repository name.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.put(
            f"{GITHUB_API}/user/starred/{owner}/{repo}",
            headers=_headers(),
            timeout=30,
        )
        resp.raise_for_status()
    return json.dumps({"starred": True, "repo": f"{owner}/{repo}"})


# ── 32. Unstar Repository ───────────────────────────────────────────────────

@mcp_server.tool()
async def unstar_repository(owner: str, repo: str) -> str:
    """Unstar a GitHub repository.

    Args:
        owner: Repository owner.
        repo: Repository name.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.delete(
            f"{GITHUB_API}/user/starred/{owner}/{repo}",
            headers=_headers(),
            timeout=30,
        )
        resp.raise_for_status()
    return json.dumps({"unstarred": True, "repo": f"{owner}/{repo}"})


# ── 33. List Starred Repositories ───────────────────────────────────────────

@mcp_server.tool()
async def list_starred_repositories(
    per_page: int = 30, page: int = 1,
) -> str:
    """List repositories starred by the authenticated user.

    Args:
        per_page: Results per page (max 100).
        page: Page number.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{GITHUB_API}/user/starred",
            headers=_headers(),
            params={"per_page": per_page, "page": page},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
    return json.dumps([
        {
            "full_name": r.get("full_name"),
            "url": r.get("html_url"),
            "description": r.get("description"),
            "stars": r.get("stargazers_count"),
            "language": r.get("language"),
        }
        for r in data
    ])


# ── 34. Fork Repository ─────────────────────────────────────────────────────

@mcp_server.tool()
async def fork_repository(
    owner: str, repo: str, organization: str = "",
) -> str:
    """Fork a GitHub repository.

    Args:
        owner: Repository owner.
        repo: Repository name.
        organization: Optional org to fork into (defaults to authenticated user).
    """
    payload: dict = {}
    if organization:
        payload["organization"] = organization
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{GITHUB_API}/repos/{owner}/{repo}/forks",
            headers=_headers(),
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
    return json.dumps({
        "full_name": data.get("full_name"),
        "url": data.get("html_url"),
        "private": data.get("private"),
        "fork": data.get("fork"),
    })


# ── 35. List Forks ──────────────────────────────────────────────────────────

@mcp_server.tool()
async def list_forks(
    owner: str, repo: str, per_page: int = 30, page: int = 1,
) -> str:
    """List forks of a GitHub repository.

    Args:
        owner: Repository owner.
        repo: Repository name.
        per_page: Results per page (max 100).
        page: Page number.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{GITHUB_API}/repos/{owner}/{repo}/forks",
            headers=_headers(),
            params={"per_page": per_page, "page": page},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
    return json.dumps([
        {
            "full_name": r.get("full_name"),
            "url": r.get("html_url"),
            "owner": r.get("owner", {}).get("login"),
            "created_at": r.get("created_at"),
        }
        for r in data
    ])


# ── 36. Create Release ──────────────────────────────────────────────────────

@mcp_server.tool()
async def create_release(
    owner: str,
    repo: str,
    tag_name: str,
    name: str = "",
    body: str = "",
    draft: bool = False,
    prerelease: bool = False,
    target_commitish: str = "",
) -> str:
    """Create a new release in a GitHub repository.

    Args:
        owner: Repository owner.
        repo: Repository name.
        tag_name: Tag name for the release (e.g. 'v1.0.0').
        name: Release title.
        body: Release description / notes.
        draft: True to create as draft.
        prerelease: True to mark as pre-release.
        target_commitish: Branch or commit SHA for the tag (defaults to default branch).
    """
    payload: dict = {
        "tag_name": tag_name,
        "name": name or tag_name,
        "body": body,
        "draft": draft,
        "prerelease": prerelease,
    }
    if target_commitish:
        payload["target_commitish"] = target_commitish
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{GITHUB_API}/repos/{owner}/{repo}/releases",
            headers=_headers(),
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
    return json.dumps({
        "id": data.get("id"),
        "tag_name": data.get("tag_name"),
        "name": data.get("name"),
        "url": data.get("html_url"),
        "draft": data.get("draft"),
        "prerelease": data.get("prerelease"),
        "created_at": data.get("created_at"),
    })


# ── 37. List Releases ───────────────────────────────────────────────────────

@mcp_server.tool()
async def list_releases(
    owner: str, repo: str, per_page: int = 30, page: int = 1,
) -> str:
    """List releases of a GitHub repository.

    Args:
        owner: Repository owner.
        repo: Repository name.
        per_page: Results per page (max 100).
        page: Page number.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{GITHUB_API}/repos/{owner}/{repo}/releases",
            headers=_headers(),
            params={"per_page": per_page, "page": page},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
    return json.dumps([
        {
            "id": r.get("id"),
            "tag_name": r.get("tag_name"),
            "name": r.get("name"),
            "url": r.get("html_url"),
            "draft": r.get("draft"),
            "prerelease": r.get("prerelease"),
            "published_at": r.get("published_at"),
        }
        for r in data
    ])


# ── 38. Delete Release ──────────────────────────────────────────────────────

@mcp_server.tool()
async def delete_release(owner: str, repo: str, release_id: int) -> str:
    """Delete a release from a GitHub repository.

    Args:
        owner: Repository owner.
        repo: Repository name.
        release_id: The ID of the release to delete.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.delete(
            f"{GITHUB_API}/repos/{owner}/{repo}/releases/{release_id}",
            headers=_headers(),
            timeout=30,
        )
        resp.raise_for_status()
    return json.dumps({"deleted": True, "release_id": release_id})


# ── 39. Create Label ────────────────────────────────────────────────────────

@mcp_server.tool()
async def create_label(
    owner: str,
    repo: str,
    name: str,
    color: str = "ededed",
    description: str = "",
) -> str:
    """Create a label in a GitHub repository.

    Args:
        owner: Repository owner.
        repo: Repository name.
        name: Label name.
        color: Label color as hex (without #), e.g. 'ff0000'.
        description: Label description.
    """
    payload: dict = {"name": name, "color": color}
    if description:
        payload["description"] = description
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{GITHUB_API}/repos/{owner}/{repo}/labels",
            headers=_headers(),
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
    return json.dumps({
        "name": data.get("name"),
        "color": data.get("color"),
        "description": data.get("description"),
        "url": data.get("url"),
    })


# ── 40. List Labels ─────────────────────────────────────────────────────────

@mcp_server.tool()
async def list_labels(
    owner: str, repo: str, per_page: int = 30, page: int = 1,
) -> str:
    """List labels in a GitHub repository.

    Args:
        owner: Repository owner.
        repo: Repository name.
        per_page: Results per page (max 100).
        page: Page number.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{GITHUB_API}/repos/{owner}/{repo}/labels",
            headers=_headers(),
            params={"per_page": per_page, "page": page},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
    return json.dumps([
        {
            "name": l.get("name"),
            "color": l.get("color"),
            "description": l.get("description"),
        }
        for l in data
    ])


# ── 41. Delete Label ────────────────────────────────────────────────────────

@mcp_server.tool()
async def delete_label(owner: str, repo: str, name: str) -> str:
    """Delete a label from a GitHub repository.

    Args:
        owner: Repository owner.
        repo: Repository name.
        name: Label name to delete.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.delete(
            f"{GITHUB_API}/repos/{owner}/{repo}/labels/{name}",
            headers=_headers(),
            timeout=30,
        )
        resp.raise_for_status()
    return json.dumps({"deleted": True, "label": name})


# ── 42. Add Collaborator ────────────────────────────────────────────────────

@mcp_server.tool()
async def add_collaborator(
    owner: str, repo: str, username: str, permission: str = "push",
) -> str:
    """Add a collaborator to a GitHub repository.

    Args:
        owner: Repository owner.
        repo: Repository name.
        username: GitHub username to add.
        permission: Permission level: pull, push, admin, maintain, triage.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.put(
            f"{GITHUB_API}/repos/{owner}/{repo}/collaborators/{username}",
            headers=_headers(),
            json={"permission": permission},
            timeout=30,
        )
        resp.raise_for_status()
    status = "invited" if resp.status_code == 201 else "already_collaborator"
    return json.dumps({"username": username, "status": status, "permission": permission})


# ── 43. Remove Collaborator ─────────────────────────────────────────────────

@mcp_server.tool()
async def remove_collaborator(owner: str, repo: str, username: str) -> str:
    """Remove a collaborator from a GitHub repository.

    Args:
        owner: Repository owner.
        repo: Repository name.
        username: GitHub username to remove.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.delete(
            f"{GITHUB_API}/repos/{owner}/{repo}/collaborators/{username}",
            headers=_headers(),
            timeout=30,
        )
        resp.raise_for_status()
    return json.dumps({"removed": True, "username": username})


# ── 44. List Collaborators ──────────────────────────────────────────────────

@mcp_server.tool()
async def list_collaborators(
    owner: str, repo: str, per_page: int = 30, page: int = 1,
) -> str:
    """List collaborators of a GitHub repository.

    Args:
        owner: Repository owner.
        repo: Repository name.
        per_page: Results per page (max 100).
        page: Page number.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{GITHUB_API}/repos/{owner}/{repo}/collaborators",
            headers=_headers(),
            params={"per_page": per_page, "page": page},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
    return json.dumps([
        {
            "login": u.get("login"),
            "url": u.get("html_url"),
            "permissions": u.get("permissions"),
        }
        for u in data
    ])


# ── 45. Get File Contents ───────────────────────────────────────────────────

@mcp_server.tool()
async def get_file_contents(
    owner: str, repo: str, file_path: str, ref: str = "",
) -> str:
    """Get the contents of a file from a GitHub repository.

    Args:
        owner: Repository owner.
        repo: Repository name.
        file_path: Path to the file in the repository.
        ref: Branch, tag, or commit SHA (defaults to default branch).
    """
    params: dict = {}
    if ref:
        params["ref"] = ref
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{GITHUB_API}/repos/{owner}/{repo}/contents/{file_path}",
            headers=_headers(),
            params=params,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
    content = ""
    if data.get("content"):
        content = base64.b64decode(data["content"]).decode("utf-8", errors="replace")
    return json.dumps({
        "name": data.get("name"),
        "path": data.get("path"),
        "sha": data.get("sha"),
        "size": data.get("size"),
        "type": data.get("type"),
        "content": content,
        "encoding": data.get("encoding"),
        "url": data.get("html_url"),
    })


# ── 46. Delete File ─────────────────────────────────────────────────────────

@mcp_server.tool()
async def delete_file(
    owner: str,
    repo: str,
    file_path: str,
    commit_message: str = "Delete file via API",
    branch: str = "",
) -> str:
    """Delete a file from a GitHub repository.

    Args:
        owner: Repository owner.
        repo: Repository name.
        file_path: Path to the file to delete.
        commit_message: Commit message for the deletion.
        branch: Branch to delete from (defaults to default branch).
    """
    # First get the file SHA
    async with httpx.AsyncClient() as client:
        params: dict = {}
        if branch:
            params["ref"] = branch
        get_resp = await client.get(
            f"{GITHUB_API}/repos/{owner}/{repo}/contents/{file_path}",
            headers=_headers(),
            params=params,
            timeout=30,
        )
        get_resp.raise_for_status()
        sha = get_resp.json()["sha"]

        payload: dict = {"message": commit_message, "sha": sha}
        if branch:
            payload["branch"] = branch
        resp = await client.delete(
            f"{GITHUB_API}/repos/{owner}/{repo}/contents/{file_path}",
            headers=_headers(),
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
    return json.dumps({
        "deleted": True,
        "file": file_path,
        "commit_sha": data.get("commit", {}).get("sha"),
    })


# ── 47. Delete Repository ───────────────────────────────────────────────────

@mcp_server.tool()
async def delete_repository(owner: str, repo: str) -> str:
    """Delete a GitHub repository. Requires admin access and delete_repo scope.

    Args:
        owner: Repository owner.
        repo: Repository name.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.delete(
            f"{GITHUB_API}/repos/{owner}/{repo}",
            headers=_headers(),
            timeout=30,
        )
        resp.raise_for_status()
    return json.dumps({"deleted": True, "repo": f"{owner}/{repo}"})


# ── 48. Update Repository ───────────────────────────────────────────────────

@mcp_server.tool()
async def update_repository(
    owner: str,
    repo: str,
    description: str = "",
    homepage: str = "",
    private: str = "",
    has_issues: str = "",
    has_projects: str = "",
    has_wiki: str = "",
    default_branch: str = "",
    archived: str = "",
) -> str:
    """Update a GitHub repository's settings.

    Args:
        owner: Repository owner.
        repo: Repository name.
        description: New description (leave empty to skip).
        homepage: Homepage URL (leave empty to skip).
        private: 'true' or 'false' to change visibility (leave empty to skip).
        has_issues: 'true' or 'false' to enable/disable issues (leave empty to skip).
        has_projects: 'true' or 'false' to enable/disable projects (leave empty to skip).
        has_wiki: 'true' or 'false' to enable/disable wiki (leave empty to skip).
        default_branch: New default branch name (leave empty to skip).
        archived: 'true' to archive the repo (leave empty to skip).
    """
    payload: dict = {}
    if description:
        payload["description"] = description
    if homepage:
        payload["homepage"] = homepage
    if private:
        payload["private"] = private.lower() == "true"
    if has_issues:
        payload["has_issues"] = has_issues.lower() == "true"
    if has_projects:
        payload["has_projects"] = has_projects.lower() == "true"
    if has_wiki:
        payload["has_wiki"] = has_wiki.lower() == "true"
    if default_branch:
        payload["default_branch"] = default_branch
    if archived:
        payload["archived"] = archived.lower() == "true"
    async with httpx.AsyncClient() as client:
        resp = await client.patch(
            f"{GITHUB_API}/repos/{owner}/{repo}",
            headers=_headers(),
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
    return json.dumps({
        "full_name": data.get("full_name"),
        "url": data.get("html_url"),
        "description": data.get("description"),
        "private": data.get("private"),
        "archived": data.get("archived"),
        "default_branch": data.get("default_branch"),
    })


# ── 49. List Contributors ───────────────────────────────────────────────────

@mcp_server.tool()
async def list_contributors(
    owner: str, repo: str, per_page: int = 30, page: int = 1,
) -> str:
    """List contributors to a GitHub repository.

    Args:
        owner: Repository owner.
        repo: Repository name.
        per_page: Results per page (max 100).
        page: Page number.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{GITHUB_API}/repos/{owner}/{repo}/contributors",
            headers=_headers(),
            params={"per_page": per_page, "page": page},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
    return json.dumps([
        {
            "login": c.get("login"),
            "contributions": c.get("contributions"),
            "url": c.get("html_url"),
        }
        for c in data
    ])


# ── 50. Get Repository Languages ────────────────────────────────────────────

@mcp_server.tool()
async def get_repo_languages(owner: str, repo: str) -> str:
    """Get the language breakdown of a GitHub repository.

    Args:
        owner: Repository owner.
        repo: Repository name.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{GITHUB_API}/repos/{owner}/{repo}/languages",
            headers=_headers(),
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
    return json.dumps(data)


# ── 51. List Tags ───────────────────────────────────────────────────────────

@mcp_server.tool()
async def list_tags(
    owner: str, repo: str, per_page: int = 30, page: int = 1,
) -> str:
    """List tags in a GitHub repository.

    Args:
        owner: Repository owner.
        repo: Repository name.
        per_page: Results per page (max 100).
        page: Page number.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{GITHUB_API}/repos/{owner}/{repo}/tags",
            headers=_headers(),
            params={"per_page": per_page, "page": page},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
    return json.dumps([
        {
            "name": t.get("name"),
            "sha": t.get("commit", {}).get("sha"),
            "tarball_url": t.get("tarball_url"),
            "zipball_url": t.get("zipball_url"),
        }
        for t in data
    ])


# ── 52. List Repository Topics ──────────────────────────────────────────────

@mcp_server.tool()
async def list_repo_topics(owner: str, repo: str) -> str:
    """List topics (tags) of a GitHub repository.

    Args:
        owner: Repository owner.
        repo: Repository name.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{GITHUB_API}/repos/{owner}/{repo}/topics",
            headers={**_headers(), "Accept": "application/vnd.github.mercy-preview+json"},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
    return json.dumps({"names": data.get("names", [])})


# ── 53. Update Repository Topics ────────────────────────────────────────────

@mcp_server.tool()
async def update_repo_topics(owner: str, repo: str, topics: str) -> str:
    """Replace all topics on a GitHub repository.

    Args:
        owner: Repository owner.
        repo: Repository name.
        topics: Comma-separated list of topic names (e.g. 'python,machine-learning,api').
    """
    names = [t.strip().lower() for t in topics.split(",") if t.strip()]
    async with httpx.AsyncClient() as client:
        resp = await client.put(
            f"{GITHUB_API}/repos/{owner}/{repo}/topics",
            headers={**_headers(), "Accept": "application/vnd.github.mercy-preview+json"},
            json={"names": names},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
    return json.dumps({"names": data.get("names", [])})


# ── 54. Create Gist ─────────────────────────────────────────────────────────

@mcp_server.tool()
async def create_gist(
    description: str,
    filename: str,
    content: str,
    public: bool = True,
) -> str:
    """Create a new GitHub Gist.

    Args:
        description: Gist description.
        filename: Name for the file in the gist (e.g. 'hello.py').
        content: File content.
        public: True for public, False for secret.
    """
    payload = {
        "description": description,
        "public": public,
        "files": {filename: {"content": content}},
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{GITHUB_API}/gists",
            headers=_headers(),
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
    return json.dumps({
        "id": data.get("id"),
        "url": data.get("html_url"),
        "description": data.get("description"),
        "public": data.get("public"),
        "created_at": data.get("created_at"),
    })


# ── 55. List Gists ──────────────────────────────────────────────────────────

@mcp_server.tool()
async def list_gists(per_page: int = 30, page: int = 1) -> str:
    """List gists for the authenticated user.

    Args:
        per_page: Results per page (max 100).
        page: Page number.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{GITHUB_API}/gists",
            headers=_headers(),
            params={"per_page": per_page, "page": page},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
    return json.dumps([
        {
            "id": g.get("id"),
            "url": g.get("html_url"),
            "description": g.get("description"),
            "public": g.get("public"),
            "files": list(g.get("files", {}).keys()),
            "created_at": g.get("created_at"),
            "updated_at": g.get("updated_at"),
        }
        for g in data
    ])


# ── 56. Get Gist ────────────────────────────────────────────────────────────

@mcp_server.tool()
async def get_gist(gist_id: str) -> str:
    """Get a specific gist by ID.

    Args:
        gist_id: The ID of the gist.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{GITHUB_API}/gists/{gist_id}",
            headers=_headers(),
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
    files = {}
    for fname, finfo in data.get("files", {}).items():
        files[fname] = {
            "filename": finfo.get("filename"),
            "language": finfo.get("language"),
            "size": finfo.get("size"),
            "content": finfo.get("content"),
        }
    return json.dumps({
        "id": data.get("id"),
        "url": data.get("html_url"),
        "description": data.get("description"),
        "public": data.get("public"),
        "files": files,
        "created_at": data.get("created_at"),
    })


# ── 57. Delete Gist ─────────────────────────────────────────────────────────

@mcp_server.tool()
async def delete_gist(gist_id: str) -> str:
    """Delete a gist.

    Args:
        gist_id: The ID of the gist to delete.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.delete(
            f"{GITHUB_API}/gists/{gist_id}",
            headers=_headers(),
            timeout=30,
        )
        resp.raise_for_status()
    return json.dumps({"deleted": True, "gist_id": gist_id})


# ── 58. List Workflows ──────────────────────────────────────────────────────

@mcp_server.tool()
async def list_workflows(
    owner: str, repo: str, per_page: int = 30, page: int = 1,
) -> str:
    """List GitHub Actions workflows in a repository.

    Args:
        owner: Repository owner.
        repo: Repository name.
        per_page: Results per page (max 100).
        page: Page number.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{GITHUB_API}/repos/{owner}/{repo}/actions/workflows",
            headers=_headers(),
            params={"per_page": per_page, "page": page},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
    return json.dumps({
        "total_count": data.get("total_count"),
        "workflows": [
            {
                "id": w.get("id"),
                "name": w.get("name"),
                "state": w.get("state"),
                "path": w.get("path"),
                "url": w.get("html_url"),
            }
            for w in data.get("workflows", [])
        ],
    })


# ── 59. Trigger Workflow Dispatch ────────────────────────────────────────────

@mcp_server.tool()
async def trigger_workflow(
    owner: str,
    repo: str,
    workflow_id: str,
    ref: str = "main",
    inputs: str = "",
) -> str:
    """Trigger a GitHub Actions workflow dispatch event.

    Args:
        owner: Repository owner.
        repo: Repository name.
        workflow_id: Workflow ID or filename (e.g. 'ci.yml').
        ref: Git ref to run the workflow on (branch or tag).
        inputs: JSON string of workflow inputs (e.g. '{"name": "value"}').
    """
    payload: dict = {"ref": ref}
    if inputs:
        payload["inputs"] = json.loads(inputs)
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{GITHUB_API}/repos/{owner}/{repo}/actions/workflows/{workflow_id}/dispatches",
            headers=_headers(),
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
    return json.dumps({"triggered": True, "workflow": workflow_id, "ref": ref})


# ── 60. List Workflow Runs ───────────────────────────────────────────────────

@mcp_server.tool()
async def list_workflow_runs(
    owner: str,
    repo: str,
    workflow_id: str = "",
    status: str = "",
    per_page: int = 10,
    page: int = 1,
) -> str:
    """List GitHub Actions workflow runs.

    Args:
        owner: Repository owner.
        repo: Repository name.
        workflow_id: Optional workflow ID or filename to filter by.
        status: Filter by status: queued, in_progress, completed, etc.
        per_page: Results per page (max 100).
        page: Page number.
    """
    params: dict = {"per_page": per_page, "page": page}
    if status:
        params["status"] = status
    url = f"{GITHUB_API}/repos/{owner}/{repo}/actions/runs"
    if workflow_id:
        url = f"{GITHUB_API}/repos/{owner}/{repo}/actions/workflows/{workflow_id}/runs"
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, headers=_headers(), params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
    return json.dumps({
        "total_count": data.get("total_count"),
        "runs": [
            {
                "id": r.get("id"),
                "name": r.get("name"),
                "status": r.get("status"),
                "conclusion": r.get("conclusion"),
                "url": r.get("html_url"),
                "head_branch": r.get("head_branch"),
                "created_at": r.get("created_at"),
            }
            for r in data.get("workflow_runs", [])
        ],
    })


# ── 61. Cancel Workflow Run ──────────────────────────────────────────────────

@mcp_server.tool()
async def cancel_workflow_run(owner: str, repo: str, run_id: int) -> str:
    """Cancel a GitHub Actions workflow run.

    Args:
        owner: Repository owner.
        repo: Repository name.
        run_id: The ID of the workflow run to cancel.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{GITHUB_API}/repos/{owner}/{repo}/actions/runs/{run_id}/cancel",
            headers=_headers(),
            timeout=30,
        )
        resp.raise_for_status()
    return json.dumps({"cancelled": True, "run_id": run_id})


# ── 62. Re-run Workflow ─────────────────────────────────────────────────────

@mcp_server.tool()
async def rerun_workflow(owner: str, repo: str, run_id: int) -> str:
    """Re-run a GitHub Actions workflow run.

    Args:
        owner: Repository owner.
        repo: Repository name.
        run_id: The ID of the workflow run to re-run.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{GITHUB_API}/repos/{owner}/{repo}/actions/runs/{run_id}/rerun",
            headers=_headers(),
            timeout=30,
        )
        resp.raise_for_status()
    return json.dumps({"rerun": True, "run_id": run_id})


# ── 63. List Organizations ──────────────────────────────────────────────────

@mcp_server.tool()
async def list_organizations(per_page: int = 30, page: int = 1) -> str:
    """List organizations the authenticated user belongs to.

    Args:
        per_page: Results per page (max 100).
        page: Page number.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{GITHUB_API}/user/orgs",
            headers=_headers(),
            params={"per_page": per_page, "page": page},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
    return json.dumps([
        {
            "login": o.get("login"),
            "url": f"https://github.com/{o.get('login')}",
            "description": o.get("description"),
        }
        for o in data
    ])


# ── 64. List Org Members ────────────────────────────────────────────────────

@mcp_server.tool()
async def list_org_members(
    org: str, per_page: int = 30, page: int = 1,
) -> str:
    """List public members of a GitHub organization.

    Args:
        org: Organization name.
        per_page: Results per page (max 100).
        page: Page number.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{GITHUB_API}/orgs/{org}/members",
            headers=_headers(),
            params={"per_page": per_page, "page": page},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
    return json.dumps([
        {"login": m.get("login"), "url": m.get("html_url")}
        for m in data
    ])


# ── 65. List Org Repos ──────────────────────────────────────────────────────

@mcp_server.tool()
async def list_org_repos(
    org: str, type: str = "all", per_page: int = 30, page: int = 1,
) -> str:
    """List repositories of a GitHub organization.

    Args:
        org: Organization name.
        type: Filter by type: all, public, private, forks, sources, member.
        per_page: Results per page (max 100).
        page: Page number.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{GITHUB_API}/orgs/{org}/repos",
            headers=_headers(),
            params={"type": type, "per_page": per_page, "page": page, "sort": "updated"},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
    return json.dumps([
        {
            "name": r.get("full_name"),
            "url": r.get("html_url"),
            "private": r.get("private"),
            "language": r.get("language"),
            "stars": r.get("stargazers_count"),
        }
        for r in data
    ])


# ── 66. List Teams ──────────────────────────────────────────────────────────

@mcp_server.tool()
async def list_teams(org: str, per_page: int = 30, page: int = 1) -> str:
    """List teams in a GitHub organization.

    Args:
        org: Organization name.
        per_page: Results per page (max 100).
        page: Page number.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{GITHUB_API}/orgs/{org}/teams",
            headers=_headers(),
            params={"per_page": per_page, "page": page},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
    return json.dumps([
        {
            "name": t.get("name"),
            "slug": t.get("slug"),
            "description": t.get("description"),
            "permission": t.get("permission"),
            "privacy": t.get("privacy"),
        }
        for t in data
    ])


# ── 67. List Team Members ───────────────────────────────────────────────────

@mcp_server.tool()
async def list_team_members(
    org: str, team_slug: str, per_page: int = 30, page: int = 1,
) -> str:
    """List members of a team in a GitHub organization.

    Args:
        org: Organization name.
        team_slug: Team slug (e.g. 'engineering').
        per_page: Results per page (max 100).
        page: Page number.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{GITHUB_API}/orgs/{org}/teams/{team_slug}/members",
            headers=_headers(),
            params={"per_page": per_page, "page": page},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
    return json.dumps([
        {"login": m.get("login"), "url": m.get("html_url")}
        for m in data
    ])


# ── 68. Create Webhook ──────────────────────────────────────────────────────

@mcp_server.tool()
async def create_webhook(
    owner: str,
    repo: str,
    url: str,
    content_type: str = "json",
    events: str = "push",
    active: bool = True,
) -> str:
    """Create a webhook for a GitHub repository.

    Args:
        owner: Repository owner.
        repo: Repository name.
        url: Payload delivery URL.
        content_type: Content type: json or form.
        events: Comma-separated events to trigger (e.g. 'push,pull_request').
        active: Whether the webhook is active.
    """
    event_list = [e.strip() for e in events.split(",")]
    payload = {
        "config": {"url": url, "content_type": content_type},
        "events": event_list,
        "active": active,
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{GITHUB_API}/repos/{owner}/{repo}/hooks",
            headers=_headers(),
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
    return json.dumps({
        "id": data.get("id"),
        "url": data.get("url"),
        "events": data.get("events"),
        "active": data.get("active"),
        "created_at": data.get("created_at"),
    })


# ── 69. List Webhooks ───────────────────────────────────────────────────────

@mcp_server.tool()
async def list_webhooks(
    owner: str, repo: str, per_page: int = 30, page: int = 1,
) -> str:
    """List webhooks for a GitHub repository.

    Args:
        owner: Repository owner.
        repo: Repository name.
        per_page: Results per page (max 100).
        page: Page number.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{GITHUB_API}/repos/{owner}/{repo}/hooks",
            headers=_headers(),
            params={"per_page": per_page, "page": page},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
    return json.dumps([
        {
            "id": h.get("id"),
            "url": h.get("config", {}).get("url"),
            "events": h.get("events"),
            "active": h.get("active"),
        }
        for h in data
    ])


# ── 70. Delete Webhook ──────────────────────────────────────────────────────

@mcp_server.tool()
async def delete_webhook(owner: str, repo: str, hook_id: int) -> str:
    """Delete a webhook from a GitHub repository.

    Args:
        owner: Repository owner.
        repo: Repository name.
        hook_id: The ID of the webhook to delete.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.delete(
            f"{GITHUB_API}/repos/{owner}/{repo}/hooks/{hook_id}",
            headers=_headers(),
            timeout=30,
        )
        resp.raise_for_status()
    return json.dumps({"deleted": True, "hook_id": hook_id})


# ── 71. List Notifications ──────────────────────────────────────────────────

@mcp_server.tool()
async def list_notifications(
    all: bool = False, participating: bool = False, per_page: int = 30, page: int = 1,
) -> str:
    """List notifications for the authenticated user.

    Args:
        all: True to show all notifications (including read ones).
        participating: True to show only notifications you're participating in.
        per_page: Results per page (max 100).
        page: Page number.
    """
    params: dict = {"per_page": per_page, "page": page}
    if all:
        params["all"] = "true"
    if participating:
        params["participating"] = "true"
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{GITHUB_API}/notifications",
            headers=_headers(),
            params=params,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
    return json.dumps([
        {
            "id": n.get("id"),
            "reason": n.get("reason"),
            "unread": n.get("unread"),
            "subject": {
                "title": n.get("subject", {}).get("title"),
                "type": n.get("subject", {}).get("type"),
            },
            "repository": n.get("repository", {}).get("full_name"),
            "updated_at": n.get("updated_at"),
        }
        for n in data
    ])


# ── 72. Mark Notifications Read ──────────────────────────────────────────────

@mcp_server.tool()
async def mark_notifications_read() -> str:
    """Mark all notifications as read for the authenticated user."""
    async with httpx.AsyncClient() as client:
        resp = await client.put(
            f"{GITHUB_API}/notifications",
            headers=_headers(),
            json={},
            timeout=30,
        )
        resp.raise_for_status()
    return json.dumps({"marked_read": True})


# ── 73. List Deploy Keys ────────────────────────────────────────────────────

@mcp_server.tool()
async def list_deploy_keys(
    owner: str, repo: str, per_page: int = 30, page: int = 1,
) -> str:
    """List deploy keys for a GitHub repository.

    Args:
        owner: Repository owner.
        repo: Repository name.
        per_page: Results per page (max 100).
        page: Page number.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{GITHUB_API}/repos/{owner}/{repo}/keys",
            headers=_headers(),
            params={"per_page": per_page, "page": page},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
    return json.dumps([
        {
            "id": k.get("id"),
            "title": k.get("title"),
            "read_only": k.get("read_only"),
            "created_at": k.get("created_at"),
        }
        for k in data
    ])


# ── 74. Add Deploy Key ──────────────────────────────────────────────────────

@mcp_server.tool()
async def add_deploy_key(
    owner: str, repo: str, title: str, key: str, read_only: bool = True,
) -> str:
    """Add a deploy key to a GitHub repository.

    Args:
        owner: Repository owner.
        repo: Repository name.
        title: A label for the key.
        key: The public SSH key content.
        read_only: True for read-only access, False for read-write.
    """
    payload = {"title": title, "key": key, "read_only": read_only}
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{GITHUB_API}/repos/{owner}/{repo}/keys",
            headers=_headers(),
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
    return json.dumps({
        "id": data.get("id"),
        "title": data.get("title"),
        "read_only": data.get("read_only"),
        "created_at": data.get("created_at"),
    })


# ── 75. Delete Deploy Key ───────────────────────────────────────────────────

@mcp_server.tool()
async def delete_deploy_key(owner: str, repo: str, key_id: int) -> str:
    """Delete a deploy key from a GitHub repository.

    Args:
        owner: Repository owner.
        repo: Repository name.
        key_id: The ID of the deploy key to delete.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.delete(
            f"{GITHUB_API}/repos/{owner}/{repo}/keys/{key_id}",
            headers=_headers(),
            timeout=30,
        )
        resp.raise_for_status()
    return json.dumps({"deleted": True, "key_id": key_id})


# ── 76. List SSH Keys ───────────────────────────────────────────────────────

@mcp_server.tool()
async def list_ssh_keys(per_page: int = 30, page: int = 1) -> str:
    """List public SSH keys for the authenticated user.

    Args:
        per_page: Results per page (max 100).
        page: Page number.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{GITHUB_API}/user/keys",
            headers=_headers(),
            params={"per_page": per_page, "page": page},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
    return json.dumps([
        {
            "id": k.get("id"),
            "title": k.get("title"),
            "key": k.get("key"),
            "created_at": k.get("created_at"),
        }
        for k in data
    ])


# ── 77. Add SSH Key ─────────────────────────────────────────────────────────

@mcp_server.tool()
async def add_ssh_key(title: str, key: str) -> str:
    """Add a public SSH key to the authenticated user's account.

    Args:
        title: A descriptive label for the key.
        key: The public SSH key content.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{GITHUB_API}/user/keys",
            headers=_headers(),
            json={"title": title, "key": key},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
    return json.dumps({
        "id": data.get("id"),
        "title": data.get("title"),
        "created_at": data.get("created_at"),
    })


# ── 78. List GPG Keys ───────────────────────────────────────────────────────

@mcp_server.tool()
async def list_gpg_keys(per_page: int = 30, page: int = 1) -> str:
    """List GPG keys for the authenticated user.

    Args:
        per_page: Results per page (max 100).
        page: Page number.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{GITHUB_API}/user/gpg_keys",
            headers=_headers(),
            params={"per_page": per_page, "page": page},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
    return json.dumps([
        {
            "id": k.get("id"),
            "key_id": k.get("key_id"),
            "emails": [e.get("email") for e in k.get("emails", [])],
            "created_at": k.get("created_at"),
            "expires_at": k.get("expires_at"),
        }
        for k in data
    ])


# ── 79. Add GPG Key ─────────────────────────────────────────────────────────

@mcp_server.tool()
async def add_gpg_key(armored_public_key: str) -> str:
    """Add a GPG key to the authenticated user's account.

    Args:
        armored_public_key: The GPG key in ASCII-armored format.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{GITHUB_API}/user/gpg_keys",
            headers=_headers(),
            json={"armored_public_key": armored_public_key},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
    return json.dumps({
        "id": data.get("id"),
        "key_id": data.get("key_id"),
        "created_at": data.get("created_at"),
    })


# ── 80. Follow User ─────────────────────────────────────────────────────────

@mcp_server.tool()
async def follow_user(username: str) -> str:
    """Follow a GitHub user.

    Args:
        username: GitHub username to follow.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.put(
            f"{GITHUB_API}/user/following/{username}",
            headers=_headers(),
            timeout=30,
        )
        resp.raise_for_status()
    return json.dumps({"following": True, "username": username})


# ── 81. Unfollow User ───────────────────────────────────────────────────────

@mcp_server.tool()
async def unfollow_user(username: str) -> str:
    """Unfollow a GitHub user.

    Args:
        username: GitHub username to unfollow.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.delete(
            f"{GITHUB_API}/user/following/{username}",
            headers=_headers(),
            timeout=30,
        )
        resp.raise_for_status()
    return json.dumps({"unfollowed": True, "username": username})


# ── 82. List Followers ──────────────────────────────────────────────────────

@mcp_server.tool()
async def list_followers(
    username: str = "", per_page: int = 30, page: int = 1,
) -> str:
    """List followers of a user (or the authenticated user if no username given).

    Args:
        username: GitHub username (leave empty for authenticated user).
        per_page: Results per page (max 100).
        page: Page number.
    """
    url = f"{GITHUB_API}/users/{username}/followers" if username else f"{GITHUB_API}/user/followers"
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            url,
            headers=_headers(),
            params={"per_page": per_page, "page": page},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
    return json.dumps([
        {"login": u.get("login"), "url": u.get("html_url")}
        for u in data
    ])


# ── 83. List Following ──────────────────────────────────────────────────────

@mcp_server.tool()
async def list_following(
    username: str = "", per_page: int = 30, page: int = 1,
) -> str:
    """List users followed by a user (or the authenticated user if no username).

    Args:
        username: GitHub username (leave empty for authenticated user).
        per_page: Results per page (max 100).
        page: Page number.
    """
    url = f"{GITHUB_API}/users/{username}/following" if username else f"{GITHUB_API}/user/following"
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            url,
            headers=_headers(),
            params={"per_page": per_page, "page": page},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
    return json.dumps([
        {"login": u.get("login"), "url": u.get("html_url")}
        for u in data
    ])


# ── 84. Get User Emails ─────────────────────────────────────────────────────

@mcp_server.tool()
async def list_user_emails() -> str:
    """List email addresses for the authenticated user."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{GITHUB_API}/user/emails",
            headers=_headers(),
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
    return json.dumps([
        {
            "email": e.get("email"),
            "primary": e.get("primary"),
            "verified": e.get("verified"),
            "visibility": e.get("visibility"),
        }
        for e in data
    ])


# ── 85. List Milestones ─────────────────────────────────────────────────────

@mcp_server.tool()
async def list_milestones(
    owner: str, repo: str, state: str = "open", per_page: int = 30, page: int = 1,
) -> str:
    """List milestones in a GitHub repository.

    Args:
        owner: Repository owner.
        repo: Repository name.
        state: Filter by state: open, closed, all.
        per_page: Results per page (max 100).
        page: Page number.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{GITHUB_API}/repos/{owner}/{repo}/milestones",
            headers=_headers(),
            params={"state": state, "per_page": per_page, "page": page},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
    return json.dumps([
        {
            "number": m.get("number"),
            "title": m.get("title"),
            "state": m.get("state"),
            "description": m.get("description"),
            "open_issues": m.get("open_issues"),
            "closed_issues": m.get("closed_issues"),
            "due_on": m.get("due_on"),
        }
        for m in data
    ])


# ── 86. Create Milestone ────────────────────────────────────────────────────

@mcp_server.tool()
async def create_milestone(
    owner: str,
    repo: str,
    title: str,
    description: str = "",
    due_on: str = "",
    state: str = "open",
) -> str:
    """Create a milestone in a GitHub repository.

    Args:
        owner: Repository owner.
        repo: Repository name.
        title: Milestone title.
        description: Milestone description.
        due_on: Due date in ISO 8601 format (e.g. '2025-12-31T23:59:59Z').
        state: State: open or closed.
    """
    payload: dict = {"title": title, "state": state}
    if description:
        payload["description"] = description
    if due_on:
        payload["due_on"] = due_on
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{GITHUB_API}/repos/{owner}/{repo}/milestones",
            headers=_headers(),
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
    return json.dumps({
        "number": data.get("number"),
        "title": data.get("title"),
        "url": data.get("html_url"),
        "state": data.get("state"),
    })


# ── 87. List Repo Projects ──────────────────────────────────────────────────

@mcp_server.tool()
async def list_repo_projects(
    owner: str, repo: str, state: str = "open", per_page: int = 30, page: int = 1,
) -> str:
    """List projects in a GitHub repository (classic projects).

    Args:
        owner: Repository owner.
        repo: Repository name.
        state: Filter by state: open, closed, all.
        per_page: Results per page (max 100).
        page: Page number.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{GITHUB_API}/repos/{owner}/{repo}/projects",
            headers={**_headers(), "Accept": "application/vnd.github.inertia-preview+json"},
            params={"state": state, "per_page": per_page, "page": page},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
    return json.dumps([
        {
            "id": p.get("id"),
            "name": p.get("name"),
            "body": p.get("body"),
            "state": p.get("state"),
            "url": p.get("html_url"),
            "created_at": p.get("created_at"),
        }
        for p in data
    ])


# ── 88. Get Rate Limit ──────────────────────────────────────────────────────

@mcp_server.tool()
async def get_rate_limit() -> str:
    """Get the current API rate limit status for the authenticated user."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{GITHUB_API}/rate_limit",
            headers=_headers(),
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
    core = data.get("resources", {}).get("core", {})
    search = data.get("resources", {}).get("search", {})
    return json.dumps({
        "core": {
            "limit": core.get("limit"),
            "remaining": core.get("remaining"),
            "reset": core.get("reset"),
            "used": core.get("used"),
        },
        "search": {
            "limit": search.get("limit"),
            "remaining": search.get("remaining"),
            "reset": search.get("reset"),
            "used": search.get("used"),
        },
    })


# ── 89. List Packages ───────────────────────────────────────────────────────

@mcp_server.tool()
async def list_packages(
    package_type: str = "container", per_page: int = 30, page: int = 1,
) -> str:
    """List packages for the authenticated user.

    Args:
        package_type: Package type: npm, maven, rubygems, docker, nuget, container.
        per_page: Results per page (max 100).
        page: Page number.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{GITHUB_API}/user/packages",
            headers=_headers(),
            params={"package_type": package_type, "per_page": per_page, "page": page},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
    return json.dumps([
        {
            "name": p.get("name"),
            "package_type": p.get("package_type"),
            "visibility": p.get("visibility"),
            "url": p.get("html_url"),
            "created_at": p.get("created_at"),
            "updated_at": p.get("updated_at"),
        }
        for p in data
    ])


# ── 90. Delete Package ──────────────────────────────────────────────────────

@mcp_server.tool()
async def delete_package(package_type: str, package_name: str) -> str:
    """Delete a package for the authenticated user.

    Args:
        package_type: Package type: npm, maven, rubygems, docker, nuget, container.
        package_name: The name of the package to delete.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.delete(
            f"{GITHUB_API}/user/packages/{package_type}/{package_name}",
            headers=_headers(),
            timeout=30,
        )
        resp.raise_for_status()
    return json.dumps({"deleted": True, "package": package_name})


# ── 91. List Codespaces ─────────────────────────────────────────────────────

@mcp_server.tool()
async def list_codespaces(per_page: int = 30, page: int = 1) -> str:
    """List codespaces for the authenticated user.

    Args:
        per_page: Results per page (max 100).
        page: Page number.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{GITHUB_API}/user/codespaces",
            headers=_headers(),
            params={"per_page": per_page, "page": page},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
    return json.dumps({
        "total_count": data.get("total_count"),
        "codespaces": [
            {
                "name": cs.get("name"),
                "state": cs.get("state"),
                "repository": cs.get("repository", {}).get("full_name"),
                "machine": cs.get("machine", {}).get("display_name"),
                "created_at": cs.get("created_at"),
                "updated_at": cs.get("updated_at"),
                "web_url": cs.get("web_url"),
            }
            for cs in data.get("codespaces", [])
        ],
    })


# ── 92. Delete Branch ───────────────────────────────────────────────────────

@mcp_server.tool()
async def delete_branch(owner: str, repo: str, branch_name: str) -> str:
    """Delete a branch from a GitHub repository.

    Args:
        owner: Repository owner.
        repo: Repository name.
        branch_name: Name of the branch to delete.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.delete(
            f"{GITHUB_API}/repos/{owner}/{repo}/git/refs/heads/{branch_name}",
            headers=_headers(),
            timeout=30,
        )
        resp.raise_for_status()
    return json.dumps({"deleted": True, "branch": branch_name})


# ── 93. Create Tag ──────────────────────────────────────────────────────────

@mcp_server.tool()
async def create_tag(
    owner: str,
    repo: str,
    tag_name: str,
    commit_sha: str,
    message: str = "",
) -> str:
    """Create a lightweight tag (ref) on a commit.

    Args:
        owner: Repository owner.
        repo: Repository name.
        tag_name: Tag name (e.g. 'v1.0.0').
        commit_sha: The SHA of the commit to tag.
        message: Tag message (for annotated tag).
    """
    async with httpx.AsyncClient() as client:
        # Create annotated tag object if message provided
        if message:
            tag_resp = await client.post(
                f"{GITHUB_API}/repos/{owner}/{repo}/git/tags",
                headers=_headers(),
                json={
                    "tag": tag_name,
                    "message": message,
                    "object": commit_sha,
                    "type": "commit",
                },
                timeout=30,
            )
            tag_resp.raise_for_status()
            sha = tag_resp.json()["sha"]
            obj_type = "tag"
        else:
            sha = commit_sha
            obj_type = "commit"

        # Create the ref
        ref_resp = await client.post(
            f"{GITHUB_API}/repos/{owner}/{repo}/git/refs",
            headers=_headers(),
            json={"ref": f"refs/tags/{tag_name}", "sha": sha},
            timeout=30,
        )
        ref_resp.raise_for_status()
        data = ref_resp.json()
    return json.dumps({
        "ref": data.get("ref"),
        "sha": data.get("object", {}).get("sha"),
        "type": obj_type,
    })


# ── 94. Delete Tag ──────────────────────────────────────────────────────────

@mcp_server.tool()
async def delete_tag(owner: str, repo: str, tag_name: str) -> str:
    """Delete a tag from a GitHub repository.

    Args:
        owner: Repository owner.
        repo: Repository name.
        tag_name: Tag name to delete.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.delete(
            f"{GITHUB_API}/repos/{owner}/{repo}/git/refs/tags/{tag_name}",
            headers=_headers(),
            timeout=30,
        )
        resp.raise_for_status()
    return json.dumps({"deleted": True, "tag": tag_name})


# ── 95. List Check Runs ─────────────────────────────────────────────────────

@mcp_server.tool()
async def list_check_runs(owner: str, repo: str, ref: str) -> str:
    """List check runs for a specific ref (branch, tag, or SHA).

    Args:
        owner: Repository owner.
        repo: Repository name.
        ref: Git ref (branch, tag, or commit SHA).
    """
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{GITHUB_API}/repos/{owner}/{repo}/commits/{ref}/check-runs",
            headers=_headers(),
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
    return json.dumps({
        "total_count": data.get("total_count"),
        "check_runs": [
            {
                "id": cr.get("id"),
                "name": cr.get("name"),
                "status": cr.get("status"),
                "conclusion": cr.get("conclusion"),
                "url": cr.get("html_url"),
                "started_at": cr.get("started_at"),
                "completed_at": cr.get("completed_at"),
            }
            for cr in data.get("check_runs", [])
        ],
    })


# ── 96. Get Repository README ───────────────────────────────────────────────

@mcp_server.tool()
async def get_readme(owner: str, repo: str, ref: str = "") -> str:
    """Get the README content of a GitHub repository.

    Args:
        owner: Repository owner.
        repo: Repository name.
        ref: Branch, tag, or commit SHA (defaults to default branch).
    """
    params: dict = {}
    if ref:
        params["ref"] = ref
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{GITHUB_API}/repos/{owner}/{repo}/readme",
            headers=_headers(),
            params=params,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
    content = ""
    if data.get("content"):
        content = base64.b64decode(data["content"]).decode("utf-8", errors="replace")
    return json.dumps({
        "name": data.get("name"),
        "path": data.get("path"),
        "size": data.get("size"),
        "content": content,
        "url": data.get("html_url"),
    })


# ── 97. List Directory Contents ──────────────────────────────────────────────

@mcp_server.tool()
async def list_directory_contents(
    owner: str, repo: str, path: str = "", ref: str = "",
) -> str:
    """List the contents of a directory in a GitHub repository.

    Args:
        owner: Repository owner.
        repo: Repository name.
        path: Directory path (empty for root).
        ref: Branch, tag, or commit SHA (defaults to default branch).
    """
    params: dict = {}
    if ref:
        params["ref"] = ref
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{GITHUB_API}/repos/{owner}/{repo}/contents/{path}",
            headers=_headers(),
            params=params,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
    if not isinstance(data, list):
        return json.dumps({"error": "Path is a file, not a directory"})
    return json.dumps([
        {
            "name": item.get("name"),
            "path": item.get("path"),
            "type": item.get("type"),
            "size": item.get("size"),
            "url": item.get("html_url"),
        }
        for item in data
    ])


# ── 98. Compare Commits ─────────────────────────────────────────────────────

@mcp_server.tool()
async def compare_commits(
    owner: str, repo: str, base: str, head: str,
) -> str:
    """Compare two commits, branches, or tags.

    Args:
        owner: Repository owner.
        repo: Repository name.
        base: Base branch/tag/SHA.
        head: Head branch/tag/SHA.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{GITHUB_API}/repos/{owner}/{repo}/compare/{base}...{head}",
            headers=_headers(),
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
    return json.dumps({
        "status": data.get("status"),
        "ahead_by": data.get("ahead_by"),
        "behind_by": data.get("behind_by"),
        "total_commits": data.get("total_commits"),
        "url": data.get("html_url"),
        "files": [
            {
                "filename": f.get("filename"),
                "status": f.get("status"),
                "additions": f.get("additions"),
                "deletions": f.get("deletions"),
            }
            for f in data.get("files", [])[:50]  # Limit to avoid huge responses
        ],
    })


# ── 99. List Stargazers ─────────────────────────────────────────────────────

@mcp_server.tool()
async def list_stargazers(
    owner: str, repo: str, per_page: int = 30, page: int = 1,
) -> str:
    """List users who have starred a GitHub repository.

    Args:
        owner: Repository owner.
        repo: Repository name.
        per_page: Results per page (max 100).
        page: Page number.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{GITHUB_API}/repos/{owner}/{repo}/stargazers",
            headers=_headers(),
            params={"per_page": per_page, "page": page},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
    return json.dumps([
        {"login": u.get("login"), "url": u.get("html_url")}
        for u in data
    ])


# ── 100. List Repo Invitations ───────────────────────────────────────────────

@mcp_server.tool()
async def list_repo_invitations(owner: str, repo: str) -> str:
    """List pending repository invitations.

    Args:
        owner: Repository owner.
        repo: Repository name.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{GITHUB_API}/repos/{owner}/{repo}/invitations",
            headers=_headers(),
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
    return json.dumps([
        {
            "id": inv.get("id"),
            "invitee": inv.get("invitee", {}).get("login"),
            "inviter": inv.get("inviter", {}).get("login"),
            "permissions": inv.get("permissions"),
            "created_at": inv.get("created_at"),
        }
        for inv in data
    ])


# ── 101. List Security Advisories ───────────────────────────────────────────

@mcp_server.tool()
async def list_security_advisories(
    owner: str, repo: str, state: str = "published",
) -> str:
    """List security advisories for a repository.

    Args:
        owner: Repository owner.
        repo: Repository name.
        state: Filter by state: draft, published, closed, triage.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{GITHUB_API}/repos/{owner}/{repo}/security-advisories",
            headers=_headers(),
            params={"state": state},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
    return json.dumps([
        {
            "ghsa_id": a.get("ghsa_id"),
            "summary": a.get("summary"),
            "severity": a.get("severity"),
            "state": a.get("state"),
            "url": a.get("html_url"),
            "published_at": a.get("published_at"),
        }
        for a in data
    ])


# ── 102. List Deployments ───────────────────────────────────────────────────

@mcp_server.tool()
async def list_deployments(
    owner: str, repo: str, environment: str = "", per_page: int = 30, page: int = 1,
) -> str:
    """List deployments for a repository.

    Args:
        owner: Repository owner.
        repo: Repository name.
        environment: Filter by environment name (e.g. 'production').
        per_page: Results per page (max 100).
        page: Page number.
    """
    params: dict = {"per_page": per_page, "page": page}
    if environment:
        params["environment"] = environment
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{GITHUB_API}/repos/{owner}/{repo}/deployments",
            headers=_headers(),
            params=params,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
    return json.dumps([
        {
            "id": d.get("id"),
            "ref": d.get("ref"),
            "environment": d.get("environment"),
            "description": d.get("description"),
            "creator": d.get("creator", {}).get("login"),
            "created_at": d.get("created_at"),
            "updated_at": d.get("updated_at"),
        }
        for d in data
    ])


# ── 103. Create Deployment Status ───────────────────────────────────────────

@mcp_server.tool()
async def create_deployment_status(
    owner: str,
    repo: str,
    deployment_id: int,
    state: str,
    description: str = "",
    environment_url: str = "",
    log_url: str = "",
) -> str:
    """Create a deployment status.

    Args:
        owner: Repository owner.
        repo: Repository name.
        deployment_id: The deployment ID.
        state: Status: error, failure, inactive, in_progress, queued, pending, success.
        description: Short description.
        environment_url: URL of the deployment environment.
        log_url: URL for deployment logs.
    """
    payload: dict = {"state": state}
    if description:
        payload["description"] = description
    if environment_url:
        payload["environment_url"] = environment_url
    if log_url:
        payload["log_url"] = log_url
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{GITHUB_API}/repos/{owner}/{repo}/deployments/{deployment_id}/statuses",
            headers=_headers(),
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
    return json.dumps({
        "id": data.get("id"),
        "state": data.get("state"),
        "description": data.get("description"),
        "created_at": data.get("created_at"),
    })


# ── 104. List Environments ──────────────────────────────────────────────────

@mcp_server.tool()
async def list_environments(owner: str, repo: str) -> str:
    """List deployment environments for a repository.

    Args:
        owner: Repository owner.
        repo: Repository name.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{GITHUB_API}/repos/{owner}/{repo}/environments",
            headers=_headers(),
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
    return json.dumps({
        "total_count": data.get("total_count"),
        "environments": [
            {
                "name": env.get("name"),
                "url": env.get("html_url"),
                "created_at": env.get("created_at"),
                "updated_at": env.get("updated_at"),
            }
            for env in data.get("environments", [])
        ],
    })


# ── Run the MCP server via stdio ─────────────────────────────────────────────

if __name__ == "__main__":
    mcp_server.run(transport="stdio")
