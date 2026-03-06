import { NextResponse } from "next/server";
import { getServerSession } from "next-auth";
import { authOptions } from "@/app/lib/auth";
import dbConnect from "@/app/lib/db";
import User from "@/app/lib/models/User";
import { getHistory, addExchange } from "@/app/lib/memory";

// POST /api/chat  — proxy to MCP server with user's github token
export async function POST(req) {
  try {
    await dbConnect();
    const session = await getServerSession(authOptions);
    if (!session) {
      return NextResponse.json({ error: "Not authenticated" }, { status: 401 });
    }

    const { message } = await req.json();
    if (!message) {
      return NextResponse.json({ error: "message required" }, { status: 400 });
    }

    const user = await User.findOne({ username: session.user.username });
    if (!user) {
      return NextResponse.json({ error: "User not found" }, { status: 404 });
    }

    const userId = user._id.toString();
    const MCP = process.env.MCP_SERVER_URL || "http://localhost:8000";

    // Get short-term history from Redis
    const history = await getHistory(userId);

    const res = await fetch(`${MCP}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message,
        history: history.length > 0 ? history : undefined,
        github_token: user.githubToken || undefined,
        docker_username: user.dockerUsername || undefined,
        docker_pat: user.dockerPAT || undefined,
        user_id: userId,
        user_context: {
          username: user.username,
          has_github_token: !!user.githubToken,
          has_docker_token: !!(user.dockerUsername && user.dockerPAT),
          docker_username: user.dockerUsername || null,
          phone: user.phone || null,
          message_count: user.messageCount,
        },
      }),
    });

    const data = await res.json();
    const reply = data.reply || "No response from agent.";

    // Save exchange to Redis (short-term)
    await addExchange(userId, message, reply);

    user.messageCount += 1;
    await user.save();

    return NextResponse.json({ ok: true, reply });
  } catch (err) {
    return NextResponse.json({ error: err.message }, { status: 500 });
  }
}
