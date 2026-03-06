"""
MCP Docker Hub Server — a proper MCP server exposing Docker Hub operations as tools.

Run standalone:
    python docker_mcp/mcp_docker.py

The OpenAI Agent SDK connects to this via MCPServerStdio.
"""

import os
import json
import httpx
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

load_dotenv()

DOCKER_HUB_API = "https://hub.docker.com"
DOCKER_USERNAME = os.getenv("DOCKER_USERNAME", "")
DOCKER_PAT = os.getenv("DOCKER_PAT", "")

mcp_server = FastMCP("Docker Hub MCP Server")

# ── Internal: get a bearer token ─────────────────────────────────────────────

_cached_token: str | None = None


async def _get_bearer_token() -> str:
    """Authenticate with Docker Hub and return a short-lived bearer token."""
    global _cached_token
    if _cached_token:
        return _cached_token

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{DOCKER_HUB_API}/v2/auth/token",
            json={"identifier": DOCKER_USERNAME, "secret": DOCKER_PAT},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
    _cached_token = data.get("access_token") or data.get("token", "")
    return _cached_token


async def _headers() -> dict:
    """Common headers with bearer auth for Docker Hub API calls."""
    token = await _get_bearer_token()
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


async def _authed_request(method: str, url: str, **kwargs) -> httpx.Response:
    """Make an authenticated request, retrying once if token expired."""
    global _cached_token
    headers = await _headers()
    async with httpx.AsyncClient() as client:
        resp = await client.request(method, url, headers=headers, timeout=30, **kwargs)
        if resp.status_code == 401:
            # Token expired — refresh and retry
            _cached_token = None
            headers = await _headers()
            resp = await client.request(method, url, headers=headers, timeout=30, **kwargs)
    return resp


# ══════════════════════════════════════════════════════════════════════════════
#  REPOSITORIES
# ══════════════════════════════════════════════════════════════════════════════

# ── 1. List Repositories ─────────────────────────────────────────────────────

@mcp_server.tool()
async def list_docker_repositories(
    namespace: str = "",
    page: int = 1,
    page_size: int = 25,
) -> str:
    """List Docker Hub repositories for a namespace (user or org).

    Args:
        namespace: Docker Hub namespace (username or org). Defaults to authenticated user.
        page: Page number (default 1).
        page_size: Items per page (max 100, default 25).
    """
    ns = namespace or DOCKER_USERNAME
    resp = await _authed_request(
        "GET",
        f"{DOCKER_HUB_API}/v2/namespaces/{ns}/repositories",
        params={"page": page, "page_size": page_size},
    )
    resp.raise_for_status()
    data = resp.json()
    repos = [
        {
            "name": r.get("name"),
            "namespace": r.get("namespace"),
            "description": r.get("description", ""),
            "is_private": r.get("is_private"),
            "star_count": r.get("star_count"),
            "pull_count": r.get("pull_count"),
            "last_updated": r.get("last_updated"),
        }
        for r in data.get("results", [])
    ]
    return json.dumps({"count": data.get("count", 0), "repositories": repos})


# ── 2. Get Repository Details ────────────────────────────────────────────────

@mcp_server.tool()
async def get_docker_repository(namespace: str, repository: str) -> str:
    """Get details of a Docker Hub repository.

    Args:
        namespace: Docker Hub namespace (user or org).
        repository: Repository name.
    """
    resp = await _authed_request(
        "GET",
        f"{DOCKER_HUB_API}/v2/namespaces/{namespace}/repositories/{repository}",
    )
    resp.raise_for_status()
    d = resp.json()
    return json.dumps({
        "name": d.get("name"),
        "namespace": d.get("namespace"),
        "description": d.get("description"),
        "full_description": (d.get("full_description") or "")[:500],
        "is_private": d.get("is_private"),
        "star_count": d.get("star_count"),
        "pull_count": d.get("pull_count"),
        "last_updated": d.get("last_updated"),
        "collaborator_count": d.get("collaborator_count"),
        "status_description": d.get("status_description"),
    })


# ── 3. Create Repository ────────────────────────────────────────────────────

@mcp_server.tool()
async def create_docker_repository(
    name: str,
    namespace: str = "",
    description: str = "",
    full_description: str = "",
    is_private: bool = False,
) -> str:
    """Create a new Docker Hub repository.

    Args:
        name: Repository name (lowercase, 2-255 chars).
        namespace: Docker Hub namespace. Defaults to authenticated user.
        description: Short description (max 100 chars).
        full_description: Full description / README (max 25000 chars).
        is_private: Whether the repository is private.
    """
    ns = namespace or DOCKER_USERNAME
    payload = {
        "name": name,
        "namespace": ns,
        "description": description,
        "full_description": full_description,
        "is_private": is_private,
        "registry": "docker.io",
    }
    resp = await _authed_request(
        "POST",
        f"{DOCKER_HUB_API}/v2/namespaces/{ns}/repositories",
        json=payload,
    )
    resp.raise_for_status()
    d = resp.json()
    return json.dumps({
        "name": d.get("name"),
        "namespace": d.get("namespace"),
        "is_private": d.get("is_private"),
        "status_description": d.get("status_description"),
    })


# ══════════════════════════════════════════════════════════════════════════════
#  TAGS & IMAGES
# ══════════════════════════════════════════════════════════════════════════════

# ── 4. List Repository Tags ─────────────────────────────────────────────────

@mcp_server.tool()
async def list_docker_tags(
    namespace: str,
    repository: str,
    page: int = 1,
    page_size: int = 25,
) -> str:
    """List tags for a Docker Hub repository.

    Args:
        namespace: Docker Hub namespace.
        repository: Repository name.
        page: Page number.
        page_size: Items per page (max 100).
    """
    resp = await _authed_request(
        "GET",
        f"{DOCKER_HUB_API}/v2/namespaces/{namespace}/repositories/{repository}/tags",
        params={"page": page, "page_size": page_size},
    )
    resp.raise_for_status()
    data = resp.json()
    tags = [
        {
            "name": t.get("name"),
            "full_size": t.get("full_size"),
            "last_updated": t.get("last_updated"),
            "status": t.get("status"),
            "tag_last_pushed": t.get("tag_last_pushed"),
            "tag_last_pulled": t.get("tag_last_pulled"),
        }
        for t in data.get("results", [])
    ]
    return json.dumps({"count": data.get("count", 0), "tags": tags})


# ── 5. Get Tag Details ───────────────────────────────────────────────────────

@mcp_server.tool()
async def get_docker_tag(namespace: str, repository: str, tag: str) -> str:
    """Get details for a specific tag in a Docker Hub repository.

    Args:
        namespace: Docker Hub namespace.
        repository: Repository name.
        tag: Tag name (e.g. 'latest', 'v1.0').
    """
    resp = await _authed_request(
        "GET",
        f"{DOCKER_HUB_API}/v2/namespaces/{namespace}/repositories/{repository}/tags/{tag}",
    )
    resp.raise_for_status()
    d = resp.json()
    images = d.get("images", [])
    if isinstance(images, dict):
        images = [images]
    image_info = [
        {
            "architecture": img.get("architecture"),
            "os": img.get("os"),
            "size": img.get("size"),
            "digest": img.get("digest"),
            "status": img.get("status"),
        }
        for img in images
    ]
    return json.dumps({
        "name": d.get("name"),
        "full_size": d.get("full_size"),
        "last_updated": d.get("last_updated"),
        "status": d.get("status"),
        "images": image_info,
    })


# ══════════════════════════════════════════════════════════════════════════════
#  PERSONAL ACCESS TOKENS
# ══════════════════════════════════════════════════════════════════════════════

# ── 6. List Personal Access Tokens ───────────────────────────────────────────

@mcp_server.tool()
async def list_docker_access_tokens(page: int = 1, page_size: int = 10) -> str:
    """List personal access tokens for the authenticated Docker Hub user.

    Args:
        page: Page number.
        page_size: Items per page.
    """
    resp = await _authed_request(
        "GET",
        f"{DOCKER_HUB_API}/v2/access-tokens",
        params={"page": page, "page_size": page_size},
    )
    resp.raise_for_status()
    data = resp.json()
    tokens = [
        {
            "uuid": t.get("uuid"),
            "token_label": t.get("token_label"),
            "is_active": t.get("is_active"),
            "scopes": t.get("scopes"),
            "created_at": t.get("created_at"),
            "last_used": t.get("last_used"),
            "expires_at": t.get("expires_at"),
        }
        for t in data.get("results", [])
    ]
    return json.dumps({
        "count": data.get("count", 0),
        "active_count": data.get("active_count", 0),
        "tokens": tokens,
    })


# ── 7. Create Personal Access Token ─────────────────────────────────────────

@mcp_server.tool()
async def create_docker_access_token(
    token_label: str,
    scopes: list[str] | None = None,
    expires_at: str = "",
) -> str:
    """Create a new Docker Hub personal access token.

    Args:
        token_label: Friendly name for the token (1-100 chars).
        scopes: Token scopes, e.g. ["repo:read"]. Valid: repo:admin, repo:write, repo:read, repo:public_read.
        expires_at: Optional ISO datetime expiration (e.g. "2025-12-31T00:00:00Z").
    """
    payload: dict = {
        "token_label": token_label,
        "scopes": scopes or ["repo:read"],
    }
    if expires_at:
        payload["expires_at"] = expires_at

    resp = await _authed_request(
        "POST",
        f"{DOCKER_HUB_API}/v2/access-tokens",
        json=payload,
    )
    resp.raise_for_status()
    d = resp.json()
    return json.dumps({
        "uuid": d.get("uuid"),
        "token_label": d.get("token_label"),
        "token": d.get("token"),
        "scopes": d.get("scopes"),
        "is_active": d.get("is_active"),
        "created_at": d.get("created_at"),
        "expires_at": d.get("expires_at"),
    })


# ── 8. Get Personal Access Token ────────────────────────────────────────────

@mcp_server.tool()
async def get_docker_access_token(uuid: str) -> str:
    """Get a personal access token by UUID.

    Args:
        uuid: The UUID of the access token.
    """
    resp = await _authed_request(
        "GET",
        f"{DOCKER_HUB_API}/v2/access-tokens/{uuid}",
    )
    resp.raise_for_status()
    d = resp.json()
    return json.dumps({
        "uuid": d.get("uuid"),
        "token_label": d.get("token_label"),
        "is_active": d.get("is_active"),
        "scopes": d.get("scopes"),
        "created_at": d.get("created_at"),
        "last_used": d.get("last_used"),
        "expires_at": d.get("expires_at"),
    })


# ── 9. Update Personal Access Token ─────────────────────────────────────────

@mcp_server.tool()
async def update_docker_access_token(
    uuid: str,
    token_label: str = "",
    is_active: bool | None = None,
) -> str:
    """Update a Docker Hub personal access token (rename or enable/disable).

    Args:
        uuid: The UUID of the access token.
        token_label: New label for the token (optional).
        is_active: Set True to enable, False to disable (optional).
    """
    payload: dict = {}
    if token_label:
        payload["token_label"] = token_label
    if is_active is not None:
        payload["is_active"] = is_active

    resp = await _authed_request(
        "PATCH",
        f"{DOCKER_HUB_API}/v2/access-tokens/{uuid}",
        json=payload,
    )
    resp.raise_for_status()
    d = resp.json()
    return json.dumps({
        "uuid": d.get("uuid"),
        "token_label": d.get("token_label"),
        "is_active": d.get("is_active"),
        "scopes": d.get("scopes"),
    })


# ── 10. Delete Personal Access Token ────────────────────────────────────────

@mcp_server.tool()
async def delete_docker_access_token(uuid: str) -> str:
    """Delete a Docker Hub personal access token permanently.

    Args:
        uuid: The UUID of the access token to delete.
    """
    resp = await _authed_request(
        "DELETE",
        f"{DOCKER_HUB_API}/v2/access-tokens/{uuid}",
    )
    if resp.status_code == 204:
        return json.dumps({"deleted": True, "uuid": uuid})
    resp.raise_for_status()
    return json.dumps({"deleted": False, "detail": resp.text})


# ══════════════════════════════════════════════════════════════════════════════
#  SEARCH (Docker Hub v1 search — public)
# ══════════════════════════════════════════════════════════════════════════════

@mcp_server.tool()
async def search_docker_images(
    query: str,
    page: int = 1,
    page_size: int = 25,
) -> str:
    """Search Docker Hub for public images.

    Args:
        query: Search query string (e.g. 'nginx', 'python').
        page: Page number.
        page_size: Results per page (max 100).
    """
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{DOCKER_HUB_API}/v2/search/repositories",
            params={"query": query, "page": page, "page_size": page_size},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
    results = [
        {
            "repo_name": r.get("repo_name") or r.get("name"),
            "short_description": r.get("short_description", ""),
            "star_count": r.get("star_count"),
            "pull_count": r.get("pull_count"),
            "is_official": r.get("is_official"),
            "is_automated": r.get("is_automated"),
        }
        for r in data.get("results", [])
    ]
    return json.dumps({"count": data.get("count", 0), "results": results})


# ══════════════════════════════════════════════════════════════════════════════
#  USER PROFILE
# ══════════════════════════════════════════════════════════════════════════════

@mcp_server.tool()
async def get_docker_user_profile() -> str:
    """Get the authenticated Docker Hub user's profile information."""
    # Docker Hub v2 user profile uses the legacy endpoint
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{DOCKER_HUB_API}/v2/users/{DOCKER_USERNAME}",
            timeout=30,
        )
        resp.raise_for_status()
        d = resp.json()
    return json.dumps({
        "id": d.get("id"),
        "username": d.get("username"),
        "full_name": d.get("full_name"),
        "location": d.get("location"),
        "company": d.get("company"),
        "date_joined": d.get("date_joined"),
        "type": d.get("type"),
        "gravatar_url": d.get("gravatar_url"),
    })


# ══════════════════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    mcp_server.run(transport="stdio")
