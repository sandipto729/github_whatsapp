"use client";

import { useState } from "react";
import { signIn, useSession } from "next-auth/react";
import { useRouter } from "next/navigation";

export default function Home() {
  const router = useRouter();
  const { data: session, status } = useSession();
  const [isLogin, setIsLogin] = useState(true);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [phone, setPhone] = useState("");
  const [githubToken, setGithubToken] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  // If already logged in, redirect
  if (status === "authenticated") {
    router.push("/dashboard");
    return null;
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      if (!isLogin) {
        // Register first
        const regRes = await fetch("/api/auth/register", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ username, password, phone, githubToken }),
        });
        const regData = await regRes.json();
        if (!regRes.ok) {
          setError(regData.error || "Registration failed");
          setLoading(false);
          return;
        }
      }

      // Sign in via NextAuth
      const result = await signIn("credentials", {
        username,
        password,
        redirect: false,
      });

      if (result?.error) {
        setError("Invalid credentials");
        setLoading(false);
        return;
      }

      router.push("/dashboard");
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  if (status === "loading") {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <p className="text-zinc-400">Loading...</p>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center px-4">
      <div className="w-full max-w-md">
        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold mb-2">🐙 GitHub Assistant</h1>
          <p className="text-zinc-400 text-sm">Manage your GitHub from Telegram</p>
        </div>

        <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-6">
          <div className="flex mb-6 bg-zinc-800 rounded-lg p-1">
            <button
              onClick={() => { setIsLogin(true); setError(""); }}
              className={`flex-1 py-2 rounded-md text-sm font-medium transition ${
                isLogin ? "bg-white text-black" : "text-zinc-400 hover:text-white"
              }`}
            >
              Login
            </button>
            <button
              onClick={() => { setIsLogin(false); setError(""); }}
              className={`flex-1 py-2 rounded-md text-sm font-medium transition ${
                !isLogin ? "bg-white text-black" : "text-zinc-400 hover:text-white"
              }`}
            >
              Register
            </button>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-xs text-zinc-400 mb-1">Username</label>
              <input
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                required
                className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-sm focus:outline-none focus:border-blue-500"
                placeholder="your_username"
              />
            </div>

            <div>
              <label className="block text-xs text-zinc-400 mb-1">Password</label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-sm focus:outline-none focus:border-blue-500"
                placeholder="••••••••"
              />
            </div>

            {!isLogin && (
              <>
                <div>
                  <label className="block text-xs text-zinc-400 mb-1">
                    Phone <span className="text-zinc-600">(optional)</span>
                  </label>
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
                    GitHub Token <span className="text-zinc-600">(optional — add later too)</span>
                  </label>
                  <input
                    type="password"
                    value={githubToken}
                    onChange={(e) => setGithubToken(e.target.value)}
                    className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-sm focus:outline-none focus:border-blue-500"
                    placeholder="ghp_xxxxxxxxxxxx"
                  />
                </div>
              </>
            )}

            {error && (
              <p className="text-red-400 text-xs bg-red-400/10 px-3 py-2 rounded-lg">{error}</p>
            )}

            <button
              type="submit"
              disabled={loading}
              className="w-full py-2.5 bg-white text-black font-medium rounded-lg text-sm hover:bg-zinc-200 transition disabled:opacity-50"
            >
              {loading ? "..." : isLogin ? "Login" : "Register"}
            </button>
          </form>

          {isLogin && (
            <p className="text-center text-xs text-zinc-500 mt-4">
              After login, link Telegram with: <code className="text-zinc-300">/link username password</code>
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
