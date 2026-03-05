import { NextResponse } from "next/server";

// GET /api/telegram/setup?url=https://your-domain.com
export async function GET(req) {
  const { searchParams } = new URL(req.url);
  const url = searchParams.get("url");
  const TOKEN = process.env.TELEGRAM_BOT_TOKEN;

  if (!url) {
    return NextResponse.json({ error: "url query param required" }, { status: 400 });
  }

  const webhookUrl = `${url}/api/telegram`;
  const res = await fetch(`https://api.telegram.org/bot${TOKEN}/setWebhook?url=${webhookUrl}`);
  const data = await res.json();

  return NextResponse.json({ webhookUrl, telegram: data });
}
