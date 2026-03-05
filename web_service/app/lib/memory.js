import redis from "./redis";

const MAX_MESSAGES = 10; // 5 exchanges = 10 messages (user + assistant)
const TTL_SECONDS = 3600; // 1 hour

function key(userId) {
  return `chat:history:${userId}`;
}

/**
 * Get last 5 exchanges (10 messages) for a user.
 * @param {string} userId — MongoDB _id
 * @returns {Array<{role: string, content: string}>}
 */
export async function getHistory(userId) {
  const raw = await redis.get(key(userId));
  if (!raw) return [];
  return JSON.parse(raw);
}

/**
 * Add a user+assistant exchange and keep only last 5 exchanges.
 * Resets TTL to 1 hour on every write.
 * @param {string} userId — MongoDB _id
 * @param {string} userMessage
 * @param {string} assistantMessage
 */
export async function addExchange(userId, userMessage, assistantMessage) {
  const history = await getHistory(userId);

  history.push({ role: "user", content: userMessage });
  history.push({ role: "assistant", content: assistantMessage });

  // Keep only last 5 exchanges (10 messages)
  const trimmed = history.slice(-MAX_MESSAGES);

  await redis.set(key(userId), JSON.stringify(trimmed), "EX", TTL_SECONDS);
}

/**
 * Clear history for a user.
 * @param {string} userId — MongoDB _id
 */
export async function clearHistory(userId) {
  await redis.del(key(userId));
}
