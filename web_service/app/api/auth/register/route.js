import { NextResponse } from "next/server";
import dbConnect from "@/app/lib/db";
import User from "@/app/lib/models/User";

// POST /api/auth/register
export async function POST(req) {
  try {
    await dbConnect();
    const { username, password, phone, githubToken } = await req.json();

    if (!username || !password) {
      return NextResponse.json({ error: "username and password required" }, { status: 400 });
    }

    const exists = await User.findOne({ username });
    if (exists) {
      return NextResponse.json({ error: "Username already taken" }, { status: 409 });
    }

    const user = await User.create({
      username,
      password, // plain for now — add bcrypt later if needed
      phone: phone || "",
      githubToken: githubToken || "",
    });

    return NextResponse.json({
      ok: true,
      user: { _id: user._id, username: user.username },
    });
  } catch (err) {
    return NextResponse.json({ error: err.message }, { status: 500 });
  }
}
