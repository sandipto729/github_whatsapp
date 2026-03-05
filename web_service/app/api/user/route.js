import { NextResponse } from "next/server";
import { getServerSession } from "next-auth";
import { authOptions } from "@/app/lib/auth";
import dbConnect from "@/app/lib/db";
import User from "@/app/lib/models/User";

// GET /api/user  — fetch own profile (or ?username=xxx for public lookup)
export async function GET(req) {
  try {
    await dbConnect();
    const session = await getServerSession(authOptions);
    const { searchParams } = new URL(req.url);

    // Use session username, fallback to query param
    const username = session?.user?.username || searchParams.get("username");
    if (!username) return NextResponse.json({ error: "Not authenticated" }, { status: 401 });

    const user = await User.findOne({ username }).select("-password");
    if (!user) return NextResponse.json({ error: "User not found" }, { status: 404 });

    return NextResponse.json({
      ok: true,
      user: {
        _id: user._id,
        username: user.username,
        phone: user.phone,
        githubToken: user.githubToken ? "••••" + user.githubToken.slice(-4) : "",
        hasGithub: !!user.githubToken,
        chatId: user.chatId || null,
        messageCount: user.messageCount,
        createdAt: user.createdAt,
      },
    });
  } catch (err) {
    return NextResponse.json({ error: err.message }, { status: 500 });
  }
}

// PUT /api/user  — update own profile (phone, githubToken)
export async function PUT(req) {
  try {
    await dbConnect();
    const session = await getServerSession(authOptions);
    if (!session) return NextResponse.json({ error: "Not authenticated" }, { status: 401 });

    const { phone, githubToken } = await req.json();
    const user = await User.findOne({ username: session.user.username });
    if (!user) return NextResponse.json({ error: "User not found" }, { status: 404 });

    if (phone !== undefined) user.phone = phone;
    if (githubToken !== undefined) user.githubToken = githubToken;
    await user.save();

    return NextResponse.json({ ok: true, message: "Profile updated" });
  } catch (err) {
    return NextResponse.json({ error: err.message }, { status: 500 });
  }
}
