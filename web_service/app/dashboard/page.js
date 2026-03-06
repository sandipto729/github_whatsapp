"use client";

import { useState, useEffect } from "react";
import { useSession, signOut } from "next-auth/react";
import { useRouter } from "next/navigation";

export default function Dashboard() {
  const router = useRouter();
  const { data: session, status } = useSession();
  const [user, setUser] = useState(null);
  const [phone, setPhone] = useState("");
  const [githubToken, setGithubToken] = useState("");
  const [dockerUsername, setDockerUsername] = useState("");
  const [dockerPAT, setDockerPAT] = useState("");
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState("");

  useEffect(() => {
    if (status === "unauthenticated") {
      router.push("/");
      return;
    }
    if (status === "authenticated") {
      fetchProfile(session.user.username);
    }
  }, [status]);

  async function fetchProfile(username) {
    const res = await fetch(`/api/user?username=${username}`);
    const data = await res.json();
    if (!res.ok) {
      signOut({ callbackUrl: "/" });
      return;
    }
    setUser(data.user);
    setPhone(data.user.phone || "");
  }

  async function handleSave(e) {
    e.preventDefault();
    setSaving(true);
    setMsg("");

    const body = {};
    if (phone) body.phone = phone;
    if (githubToken) body.githubToken = githubToken;
    if (dockerUsername) body.dockerUsername = dockerUsername;
    if (dockerPAT) body.dockerPAT = dockerPAT;

    const res = await fetch("/api/user", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });

    const data = await res.json();
    setSaving(false);

    if (res.ok) {
      setMsg("✅ Saved!");
      setGithubToken("");
      setDockerPAT("");
      fetchProfile(session.user.username);
    } else {
      setMsg("❌ " + data.error);
    }
  }

  if (status === "loading" || !user) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <p className="text-zinc-400">Loading...</p>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex flex-col">
      <nav className="flex items-center justify-between px-6 py-4 border-b border-zinc-800">
        <h1 className="text-lg font-bold">🐙 GitHub Assistant</h1>
        <div className="flex items-center gap-4">
          <button
            onClick={() => router.push("/chat")}
            className="px-4 py-1.5 bg-blue-600 text-white text-sm rounded-lg hover:bg-blue-700 transition"
          >
            💬 Chat
          </button>
          <button
            onClick={() => signOut({ callbackUrl: "/" })}
            className="text-zinc-400 text-sm hover:text-white transition"
          >
            Logout
          </button>
        </div>
      </nav>

      <div className="flex-1 flex items-start justify-center pt-16 px-4">
        <div className="w-full max-w-lg space-y-6">
          <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-6">
            <h2 className="text-xl font-semibold mb-4">👤 Profile</h2>
            <div className="space-y-3 text-sm">
              <div className="flex justify-between">
                <span className="text-zinc-400">Username</span>
                <span className="font-mono">{user.username}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-zinc-400">Phone</span>
                <span>{user.phone || "—"}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-zinc-400">GitHub</span>
                <span>{user.hasGithub ? `✅ ${user.githubToken}` : "❌ Not connected"}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-zinc-400">Docker Hub</span>
                <span>{user.hasDocker ? `✅ ${user.dockerUsername}` : "❌ Not connected"}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-zinc-400">Telegram</span>
                <span>{user.chatId ? "✅ Linked" : "❌ Not linked"}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-zinc-400">Messages</span>
                <span>{user.messageCount}</span>
              </div>
            </div>
          </div>

          <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-6">
            <h2 className="text-xl font-semibold mb-4">⚙️ Settings</h2>
            <form onSubmit={handleSave} className="space-y-4">
              <div>
                <label className="block text-xs text-zinc-400 mb-1">Phone</label>
                <input
                  type="text"
                  value={phone}
                  onChange={(e) => setPhone(e.target.value)}
                  className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-sm focus:outline-none focus:border-blue-500"
                  placeholder="+91XXXXXXXXXX"
                />
              </div>
              <div>
                <label className="block text-xs text-zinc-400 mb-1">
                  GitHub Token <span className="text-zinc-600">(enter new to update)</span>
                </label>
                <input
                  type="password"
                  value={githubToken}
                  onChange={(e) => setGithubToken(e.target.value)}
                  className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-sm focus:outline-none focus:border-blue-500"
                  placeholder="ghp_xxxxxxxxxxxx"
                />
                <p className="text-xs text-zinc-600 mt-1">
                  Get yours from{" "}
                  <a href="https://github.com/settings/tokens" target="_blank" className="text-blue-400 hover:underline">
                    github.com/settings/tokens
                  </a>
                </p>
              </div>

              <hr className="border-zinc-700" />

              <div>
                <label className="block text-xs text-zinc-400 mb-1">
                  Docker Hub Username
                </label>
                <input
                  type="text"
                  value={dockerUsername}
                  onChange={(e) => setDockerUsername(e.target.value)}
                  className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-sm focus:outline-none focus:border-blue-500"
                  placeholder="mydockerhubuser"
                />
              </div>
              <div>
                <label className="block text-xs text-zinc-400 mb-1">
                  Docker Hub PAT <span className="text-zinc-600">(personal access token)</span>
                </label>
                <input
                  type="password"
                  value={dockerPAT}
                  onChange={(e) => setDockerPAT(e.target.value)}
                  className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-sm focus:outline-none focus:border-blue-500"
                  placeholder="dckr_pat_xxxxxxxxxxxx"
                />
                <p className="text-xs text-zinc-600 mt-1">
                  Get yours from{" "}
                  <a href="https://hub.docker.com/settings/security" target="_blank" className="text-blue-400 hover:underline">
                    hub.docker.com/settings/security
                  </a>
                </p>
              </div>

              {msg && <p className="text-sm">{msg}</p>}

              <button
                type="submit"
                disabled={saving}
                className="w-full py-2.5 bg-white text-black font-medium rounded-lg text-sm hover:bg-zinc-200 transition disabled:opacity-50"
              >
                {saving ? "Saving..." : "Save Changes"}
              </button>
            </form>
          </div>

          {!user.chatId && (
            <div className="bg-blue-500/10 border border-blue-500/20 rounded-xl p-5 text-sm">
              <h3 className="font-semibold text-blue-400 mb-2">📱 Connect Telegram</h3>
              <p className="text-zinc-300 mb-2">
                1. Open the bot:{" "}
                <a
                  href="https://web.telegram.org/k/#@github_mcp_bot"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-blue-400 hover:underline"
                >
                  @github_mcp_bot
                </a>
              </p>
              <p className="text-zinc-300 mb-2">
                2. Send <strong>/start</strong>, then link your account:
              </p>
              <code className="block bg-zinc-800 px-3 py-2 rounded-lg text-blue-300 text-xs">
                /link {user.username} your_password
              </code>
              <p className="text-zinc-500 mt-2 text-xs">
                This links your Telegram chat to this account so you can use GitHub commands there.
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
