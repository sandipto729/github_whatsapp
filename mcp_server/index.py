"""
Entry-point for the GitHub Agent server.

Run with:
    uvicorn index:app --reload --port 8000
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

from chat.agent import run_agent

app = FastAPI(
    title="GitHub Agent Server",
    description="Agentic chatbot powered by OpenAI Agents SDK for GitHub operations",
    version="1.0.0",
)

# CORS — allow all origins during development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request / Response models ───────────────────────────────────────────────

class ChatMessage(BaseModel):
    role: str = Field(..., description="'user' or 'assistant'")
    content: str


class ChatRequest(BaseModel):
    message: str = Field(..., description="User's message to the agent")
    history: Optional[list[ChatMessage]] = Field(
        None,
        description="Previous conversation turns for context (short-term, from Redis)",
    )
    github_token: Optional[str] = Field(
        None,
        description="User's personal GitHub token (overrides server default)",
    )
    user_context: Optional[dict] = Field(
        None,
        description="User profile info (username, has_github_token, phone, etc.)",
    )
    user_id: Optional[str] = Field(
        None,
        description="MongoDB _id — used for Mem0 long-term memory",
    )


class ChatResponse(BaseModel):
    reply: str = Field(..., description="Agent's response")


# ── Routes ──────────────────────────────────────────────────────────────────

@app.get("/", tags=["Health"])
async def health_check():
    return {"status": "ok", "message": "GitHub Agent Server is running 🚀"}


@app.post("/chat", response_model=ChatResponse, tags=["Chat"])
async def chat(req: ChatRequest):
    """Send a message to the GitHub agent and get a response."""
    try:
        history = None
        if req.history:
            history = [h.model_dump() for h in req.history]

        reply = await run_agent(
            user_message=req.message,
            conversation_history=history,
            github_token=req.github_token,
            user_context=req.user_context,
            user_id=req.user_id,
        )
        return ChatResponse(reply=reply)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("index:app", host="0.0.0.0", port=8000, reload=True)
