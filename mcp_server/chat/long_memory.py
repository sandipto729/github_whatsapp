"""
Long-term memory using Mem0 + Qdrant.

Stores and retrieves user-specific memories that persist across sessions.
Short-term (last 5 messages) is handled by Redis on the JS side.
This module handles long-term semantic memory.
"""

import os
from mem0 import Memory

# Qdrant Cloud config — reads URL + API key from .env
QDRANT_URL = os.getenv("QDRANT_URL")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")

config = {
    "vector_store": {
        "provider": "qdrant",
        "config": {
            "url": QDRANT_URL,
            "api_key": QDRANT_API_KEY,
            "collection_name": "github_assistant_memories",
        },
    },
}

memory = Memory.from_config(config)


def add_memory(user_id: str, messages: list[dict]) -> None:
    """
    Store a conversation exchange as long-term memory.

    Args:
        user_id: Unique user identifier (MongoDB _id).
        messages: List of {"role": "user"/"assistant", "content": "..."} dicts.
    """
    try:
        memory.add(messages, user_id=user_id)
    except Exception as e:
        print(f"[mem0] Failed to add memory for {user_id}: {e}")


def search_memory(user_id: str, query: str, limit: int = 5) -> str:
    """
    Search long-term memories relevant to the current query.

    Args:
        user_id: Unique user identifier.
        query: The current user message to find relevant context for.
        limit: Max number of memories to return.

    Returns:
        Formatted string of relevant memories, or empty string if none.
    """
    try:
        results = memory.search(query, user_id=user_id, limit=limit)
        if not results or not results.get("results"):
            return ""

        memories = []
        for r in results["results"]:
            mem_text = r.get("memory", "")
            if mem_text:
                memories.append(f"- {mem_text}")

        if not memories:
            return ""

        return "Relevant memories from past conversations:\n" + "\n".join(memories)
    except Exception as e:
        print(f"[mem0] Failed to search memory for {user_id}: {e}")
        return ""


def clear_memory(user_id: str) -> None:
    """Clear all long-term memories for a user."""
    try:
        memory.delete_all(user_id=user_id)
    except Exception as e:
        print(f"[mem0] Failed to clear memory for {user_id}: {e}")
