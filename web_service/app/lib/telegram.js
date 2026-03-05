function getBase() {
  return `https://api.telegram.org/bot${process.env.TELEGRAM_BOT_TOKEN}`;
}

export async function sendTelegramMessage(chatId, text, extra = {}) {
  const BASE = getBase();
  const chunks = [];
  for (let i = 0; i < text.length; i += 4096) chunks.push(text.slice(i, i + 4096));

  for (const chunk of chunks) {
    // Try Markdown first, fall back to plain text if Telegram rejects it
    let res = await fetch(`${BASE}/sendMessage`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ chat_id: chatId, text: chunk, parse_mode: "Markdown", ...extra }),
    });

    if (!res.ok) {
      console.error("Telegram Markdown failed, retrying plain:", await res.text());
      // Retry without parse_mode
      res = await fetch(`${BASE}/sendMessage`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ chat_id: chatId, text: chunk, ...extra }),
      });
      if (!res.ok) {
        console.error("Telegram plain also failed:", await res.text());
      }
    }
  }
}

export async function sendTyping(chatId) {
  const BASE = getBase();
  await fetch(`${BASE}/sendChatAction`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ chat_id: chatId, action: "typing" }),
  });
}
