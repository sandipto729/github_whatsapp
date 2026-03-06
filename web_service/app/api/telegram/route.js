import { NextResponse } from "next/server";
import dbConnect from "@/app/lib/db";
import User from "@/app/lib/models/User";
import { sendTelegramMessage, sendTyping } from "@/app/lib/telegram";
import { getHistory, addExchange, clearHistory } from "@/app/lib/memory";

const MCP = process.env.MCP_SERVER_URL || "http://localhost:8000";
const APP_URL = process.env.NEXT_PUBLIC_APP_URL || "http://localhost:3000";

// POST /api/telegram  — Telegram webhook
export async function POST(req) {
  try {
    await dbConnect();
    const body = await req.json();
    const msg = body?.message;
    if (!msg) return NextResponse.json({ ok: true });

    const chatId = String(msg.chat.id);
    const from = msg.from;
    const text = msg.text;
    if (!text) return NextResponse.json({ ok: true });

    // Find user by chatId (linked after login on website)
    let user = await User.findOne({ chatId });

    // /start — always respond, link account if not linked
    if (text.trim().toLowerCase() === "/start") {
      if (!user) {
        await sendTelegramMessage(chatId,
          `👋 Welcome to *DevOps Assistant Bot*!\n\n`
          + `I can help you with *GitHub* and *Docker Hub* operations.\n\n`
          + `To use me, you need to register first:\n`
          + `🔗 [Register here](${APP_URL})\n\n`
          + `After registering, come back and type /link to connect your Telegram.`,
          { parse_mode: "Markdown" }
        );
      } else {
        const missingCreds = [];
        if (!user.githubToken) missingCreds.push("🐙 GitHub token");
        if (!(user.dockerUsername && user.dockerPAT)) missingCreds.push("🐳 Docker Hub credentials");
        const credsWarning = missingCreds.length > 0
          ? `\n\n⚠️ *Missing:* ${missingCreds.join(", ")}\nAdd them at: ${APP_URL}/dashboard`
          : "";
        await sendTelegramMessage(chatId,
          `🚀 Welcome back *${user.username}*!\n\n`
          + `I can help with *GitHub* and *Docker Hub* operations.\n`
          + `Just type your question and I'll help you.\n\n`
          + `• /me — Your profile\n`
          + `• /clear — Clear chat history\n`
          + `• /help — All commands`
          + credsWarning,
          { parse_mode: "Markdown" }
        );
      }
      return NextResponse.json({ ok: true });
    }

    // /link <username> <password> — link telegram to website account
    if (text.trim().toLowerCase().startsWith("/link")) {
      const parts = text.trim().split(/\s+/);
      if (parts.length < 3) {
        await sendTelegramMessage(chatId,
          `⚠️ Usage: \`/link your_username your_password\`\n\n`
          + `This connects your Telegram to your website account.\n`
          + `Don't have one? Register at: ${APP_URL}`,
          { parse_mode: "Markdown" }
        );
        return NextResponse.json({ ok: true });
      }

      const [, uname, pwd] = parts;
      const found = await User.findOne({ username: uname });

      if (!found || found.password !== pwd) {
        await sendTelegramMessage(chatId, "❌ Invalid username or password. Try again or register at: " + APP_URL);
        return NextResponse.json({ ok: true });
      }

      // Link telegram chatId to this user
      found.chatId = chatId;
      found.telegramId = from.id;
      found.firstName = from.first_name || found.firstName;
      found.lastName = from.last_name || found.lastName;
      await found.save();

      await sendTelegramMessage(chatId,
        `✅ Linked! Welcome *${found.username}*.\n\n`
        + `🐙 GitHub: ${found.githubToken ? "✅ Connected" : "❌ Not set"}\n`
        + `🐳 Docker Hub: ${found.dockerUsername && found.dockerPAT ? "✅ " + found.dockerUsername : "❌ Not set"}\n\n`
        + `${!found.githubToken || !(found.dockerUsername && found.dockerPAT) ? "⚠️ Add missing credentials at: " + APP_URL + "/dashboard\n\n" : ""}`
        + `Now just type your questions here — I help with GitHub *and* Docker Hub!`,
        { parse_mode: "Markdown" }
      );
      return NextResponse.json({ ok: true });
    }

    // ── From here, user must be registered ──
    if (!user) {
      await sendTelegramMessage(chatId,
        `🔒 You're not registered yet.\n\n`
        + `1️⃣ Register at: ${APP_URL}\n`
        + `2️⃣ Come back and type: \`/link username password\`\n\n`
        + `Then you can use all GitHub & Docker Hub features!`,
        { parse_mode: "Markdown" }
      );
      return NextResponse.json({ ok: true });
    }

    // /me
    if (text.trim().toLowerCase() === "/me") {
      const ghStatus = user.githubToken ? "✅ Connected" : "❌ Not set";
      const dkStatus = user.dockerUsername && user.dockerPAT ? "✅ " + user.dockerUsername : "❌ Not set";
      const missingList = [];
      if (!user.githubToken) missingList.push("GitHub token");
      if (!(user.dockerUsername && user.dockerPAT)) missingList.push("Docker Hub credentials");
      const addHint = missingList.length > 0
        ? `\n\n⚠️ *Add missing:* ${missingList.join(", ")}\n🔗 ${APP_URL}/dashboard`
        : "";
      await sendTelegramMessage(chatId,
        `👤 *${user.username}*\n`
        + `📱 Phone: ${user.phone || "not set"}\n`
        + `🐙 GitHub: ${ghStatus}\n`
        + `🐳 Docker Hub: ${dkStatus}\n`
        + `💬 Messages: ${user.messageCount}`
        + addHint
        + `\n\n🔧 Manage profile: ${APP_URL}/dashboard`,
        { parse_mode: "Markdown" }
      );
      return NextResponse.json({ ok: true });
    }

    // /help
    if (text.trim().toLowerCase() === "/help") {
      await sendTelegramMessage(chatId,
        `📋 *Commands:*\n\n`
        + `/start — Welcome\n`
        + `/me — Your profile\n`
        + `/clear — Clear chat history\n`
        + `/help — This menu\n\n`
        + `🐙 *GitHub examples:*\n`
        + `• "Create a repo called my-app"\n`
        + `• "List my repositories"\n`
        + `• "Push a file to my-app"\n\n`
        + `🐳 *Docker Hub examples:*\n`
        + `• "List my Docker Hub repos"\n`
        + `• "Search Docker images for nginx"\n`
        + `• "Push this repo to Docker Hub"\n`
        + `• "List tags for my-app image"\n\n`
        + `🔧 Manage settings: ${APP_URL}/dashboard`,
        { parse_mode: "Markdown" }
      );
      return NextResponse.json({ ok: true });
    }

    // /clear
    if (text.trim().toLowerCase() === "/clear") {
      await clearHistory(user._id.toString());
      await sendTelegramMessage(chatId, "🗑️ Chat history cleared!");
      return NextResponse.json({ ok: true });
    }

    // ── Forward to AI agent ──
    const missingServices = [];
    if (!user.githubToken) missingServices.push("🐙 GitHub token");
    if (!(user.dockerUsername && user.dockerPAT)) missingServices.push("🐳 Docker Hub credentials");
    if (missingServices.length === 2) {
      await sendTelegramMessage(chatId,
        `⚠️ You haven't set any credentials yet.\n\n`
        + `Missing:\n${missingServices.join("\n")}\n\n`
        + `Add them at: ${APP_URL}/dashboard\n`
        + `Then your commands will work!`,
        { parse_mode: "Markdown" }
      );
      return NextResponse.json({ ok: true });
    }

    await sendTyping(chatId);

    try {
      const userId = user._id.toString();

      // Get short-term history from Redis
      const history = await getHistory(userId);

      // Call agent
      const chatRes = await fetch(`${MCP}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: text,
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
      const chatData = await chatRes.json();
      const reply = chatData.reply || "No response from agent.";

      // Save exchange to Redis (short-term)
      await addExchange(userId, text, reply);

      user.messageCount += 1;
      await user.save();

      await sendTelegramMessage(chatId, reply);
    } catch (err) {
      await sendTelegramMessage(chatId, `❌ Error: ${err.message?.slice(0, 300)}\n\nTry /help`);
    }

    return NextResponse.json({ ok: true });
  } catch (err) {
    console.error("Telegram webhook error:", err.message);
    return NextResponse.json({ ok: true });
  }
}
