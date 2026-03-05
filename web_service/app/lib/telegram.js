function getBase() {
  return `https://api.telegram.org/bot${process.env.TELEGRAM_BOT_TOKEN}`;
}

/**
 * Escape HTML special characters so that raw text (repo names, etc.)
 * is never mangled by Telegram's HTML parser.
 */
function escapeHtml(text) {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

/**
 * Convert common Markdown patterns in the agent's reply to Telegram-safe HTML.
 * This preserves underscores in repo names (apj_abdul_kalam stays intact)
 * while still rendering bold, italic, code, and links nicely.
 */
function markdownToTelegramHtml(text) {
  let out = escapeHtml(text);

  // Code blocks: ```lang\ncode\n``` → <pre>code</pre>
  out = out.replace(/```[\w]*\n([\s\S]*?)```/g, "<pre>$1</pre>");

  // Inline code: `code` → <code>code</code>
  out = out.replace(/`([^`]+)`/g, "<code>$1</code>");

  // Bold: **text** → <b>text</b>
  out = out.replace(/\*\*(.+?)\*\*/g, "<b>$1</b>");

  // Bold: *text* (single asterisks, but NOT inside words)
  out = out.replace(/(?<!\w)\*(.+?)\*(?!\w)/g, "<b>$1</b>");

  // Markdown links: [text](url) → <a href="url">text</a>
  out = out.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2">$1</a>');

  return out;
}

/**
 * Send a message via Telegram.
 *
 * @param {string} chatId
 * @param {string} text
 * @param {object} extra  - additional Telegram API params
 * @param {"HTML"|"Markdown"|"plain"} extra.parse_mode - override parse mode
 *
 * By default, sends as HTML (safe for repo names with underscores).
 * Pass { parse_mode: "Markdown" } for hardcoded bot messages that use Markdown.
 */
export async function sendTelegramMessage(chatId, text, extra = {}) {
  const BASE = getBase();

  // Determine parse mode: caller can override, default is HTML
  const parseMode = extra.parse_mode || "HTML";
  const { parse_mode: _, ...restExtra } = extra;

  // If using HTML mode, convert agent Markdown → Telegram HTML
  const formatted = parseMode === "HTML" ? markdownToTelegramHtml(text) : text;

  const chunks = [];
  for (let i = 0; i < formatted.length; i += 4096) chunks.push(formatted.slice(i, i + 4096));

  for (const chunk of chunks) {
    // Try with parse_mode first
    let res = await fetch(`${BASE}/sendMessage`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        chat_id: chatId,
        text: chunk,
        parse_mode: parseMode !== "plain" ? parseMode : undefined,
        disable_web_page_preview: true,
        ...restExtra,
      }),
    });

    if (!res.ok) {
      console.error(`Telegram ${parseMode} failed, retrying plain:`, await res.text());
      // Retry without any formatting — send raw text (underscores still safe)
      res = await fetch(`${BASE}/sendMessage`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ chat_id: chatId, text, ...restExtra }),
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
