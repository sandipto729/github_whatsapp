# 🐙 GitHub Assistant — Telegram + Web Chat

A full-stack agentic chatbot that lets you manage your GitHub account through **Telegram** or a **web chat interface**. Powered by the **OpenAI Agents SDK**, a custom **MCP (Model Context Protocol) server** exposing 100+ GitHub API tools, and long-term memory via **Mem0 + Qdrant**.

---

## ✨ Features

- 🤖 **AI-Powered GitHub Agent** — natural language → GitHub operations  
- 💬 **Telegram Bot** — manage repos, issues, PRs, workflows straight from Telegram  
- 🌐 **Web Chat UI** — Next.js dashboard with auth, chat, and profile management  
- 🧠 **Dual Memory** — short-term (Redis, last 5 exchanges) + long-term (Mem0/Qdrant, semantic)  
- 🔐 **Per-User GitHub Tokens** — each user connects their own PAT  
- 🐳 **Docker Compose** — one-command deployment  

---

## 🏗️ Architecture

```
┌──────────────┐       ┌──────────────────┐       ┌──────────────────────┐
│   Telegram   │──────▶│                  │       │   MCP GitHub Server  │
│   Bot API    │       │   Web Service    │──────▶│   (FastMCP, stdio)   │
└──────────────┘       │   (Next.js)      │       │   104 GitHub tools   │
                       │                  │       └──────────────────────┘
┌──────────────┐       │  • Auth (NextAuth│              ▲
│   Web Chat   │──────▶│  • /api/chat     │              │
│   (Browser)  │       │  • /api/telegram │       ┌──────┴──────┐
└──────────────┘       │  • Dashboard     │       │  Agent Core │
                       └────────┬─────────┘       │  (OpenAI    │
                                │                 │   Agents SDK)│
                 ┌──────────────┼──────────┐      └──────┬──────┘
                 ▼              ▼          ▼             │
            ┌────────┐   ┌──────────┐  ┌────────┐  ┌────┴─────┐
            │MongoDB │   │  Redis   │  │ Qdrant │  │  Mem0    │
            │(Users) │   │(History) │  │(Vectors)│  │(Memory) │
            └────────┘   └──────────┘  └────────┘  └──────────┘
```

| Service | Tech | Purpose |
|---|---|---|
| **web_service** | Next.js 16, NextAuth, Tailwind CSS | Auth, dashboard, web chat, Telegram webhook |
| **mcp_server** | FastAPI, OpenAI Agents SDK, FastMCP | AI agent + MCP GitHub tool server |
| **MongoDB** | Mongoose | User accounts (credentials, GitHub token, phone) |
| **Redis** | ioredis | Short-term conversation history (last 5 exchanges, 1h TTL) |
| **Qdrant** | Qdrant Cloud | Vector store for long-term semantic memory |
| **Mem0** | mem0ai | Long-term memory layer over Qdrant |

---

## 🔧 GitHub MCP Tools (104 total)

The MCP server exposes **104 tools** covering nearly every GitHub API surface:

<details>
<summary><strong>📁 Repositories (14 tools)</strong></summary>

| # | Tool | Description |
|---|------|-------------|
| 1 | `create_repository` | Create a new repo (public/private, with README) |
| 2 | `get_repository` | Get full repo details (stars, forks, language, etc.) |
| 3 | `list_repositories` | List the authenticated user's repos |
| 48 | `update_repository` | Update settings (description, visibility, archive, etc.) |
| 47 | `delete_repository` | Delete a repo (requires `delete_repo` scope) |
| 34 | `fork_repository` | Fork a repo to your account or an org |
| 35 | `list_forks` | List forks of a repo |
| 49 | `list_contributors` | List contributors |
| 50 | `get_repo_languages` | Get language breakdown |
| 52 | `list_repo_topics` | List topics/tags |
| 53 | `update_repo_topics` | Replace all topics |
| 96 | `get_readme` | Get README content |
| 97 | `list_directory_contents` | Browse repo file tree |
| 100 | `list_repo_invitations` | List pending invitations |

</details>

<details>
<summary><strong>🌿 Branches & Tags (8 tools)</strong></summary>

| # | Tool | Description |
|---|------|-------------|
| 4 | `create_branch` | Create a branch from any source branch |
| 7 | `list_branches` | List all branches |
| 92 | `delete_branch` | Delete a branch |
| 6 | `merge_branches` | Merge one branch into another |
| 51 | `list_tags` | List tags |
| 93 | `create_tag` | Create lightweight or annotated tags |
| 94 | `delete_tag` | Delete a tag |
| 98 | `compare_commits` | Compare two branches/tags/SHAs |

</details>

<details>
<summary><strong>📄 Files (4 tools)</strong></summary>

| # | Tool | Description |
|---|------|-------------|
| 5 | `push_file` | Create or update a file on a branch |
| 45 | `get_file_contents` | Read file contents (auto-decodes base64) |
| 46 | `delete_file` | Delete a file with a commit |
| 97 | `list_directory_contents` | List directory contents |

</details>

<details>
<summary><strong>🔀 Pull Requests (7 tools)</strong></summary>

| # | Tool | Description |
|---|------|-------------|
| 8 | `create_pull_request` | Open a new PR |
| 9 | `list_pull_requests` | List PRs (open/closed/all) |
| 10 | `get_pull_request` | Get PR details (mergeable, stats, etc.) |
| 11 | `merge_pull_request` | Merge a PR (merge/squash/rebase) |
| 12 | `update_pull_request` | Update title, body, or state |
| 13 | `list_pull_request_files` | List changed files in a PR |
| 14 | `create_pull_request_review` | Submit a review (approve/request changes/comment) |

</details>

<details>
<summary><strong>🐛 Issues (6 tools)</strong></summary>

| # | Tool | Description |
|---|------|-------------|
| 15 | `create_issue` | Create an issue with labels & assignees |
| 16 | `list_issues` | List issues (filter by state, labels) |
| 17 | `get_issue` | Get full issue details |
| 18 | `update_issue` | Update title, body, state, labels, assignees |
| 19 | `add_issue_comment` | Comment on an issue or PR |
| 20 | `list_issue_comments` | List comments on an issue or PR |

</details>

<details>
<summary><strong>🔍 Search (4 tools)</strong></summary>

| # | Tool | Description |
|---|------|-------------|
| 25 | `search_repositories` | Search repos by query, language, stars |
| 26 | `search_code` | Search code across repos |
| 27 | `search_issues` | Search issues and PRs |
| 28 | `search_users` | Search users by name, location, etc. |

</details>

<details>
<summary><strong>📦 Releases (3 tools)</strong></summary>

| # | Tool | Description |
|---|------|-------------|
| 36 | `create_release` | Create a release (draft, prerelease supported) |
| 37 | `list_releases` | List releases |
| 38 | `delete_release` | Delete a release |

</details>

<details>
<summary><strong>🏷️ Labels & Milestones (5 tools)</strong></summary>

| # | Tool | Description |
|---|------|-------------|
| 39 | `create_label` | Create a label with color |
| 40 | `list_labels` | List labels |
| 41 | `delete_label` | Delete a label |
| 85 | `list_milestones` | List milestones |
| 86 | `create_milestone` | Create a milestone with due date |

</details>

<details>
<summary><strong>👥 Collaborators (3 tools)</strong></summary>

| # | Tool | Description |
|---|------|-------------|
| 42 | `add_collaborator` | Add a collaborator (pull/push/admin/maintain/triage) |
| 43 | `remove_collaborator` | Remove a collaborator |
| 44 | `list_collaborators` | List collaborators |

</details>

<details>
<summary><strong>📝 Commits & Status (5 tools)</strong></summary>

| # | Tool | Description |
|---|------|-------------|
| 21 | `list_commits` | List commits on a branch |
| 22 | `get_commit` | Get commit details (stats, changed files) |
| 23 | `get_commit_status` | Get combined CI/CD status for a ref |
| 24 | `create_commit_status` | Create a commit status (pending/success/failure) |
| 95 | `list_check_runs` | List check runs for a ref |

</details>

<details>
<summary><strong>📋 Gists (4 tools)</strong></summary>

| # | Tool | Description |
|---|------|-------------|
| 54 | `create_gist` | Create a public or secret gist |
| 55 | `list_gists` | List your gists |
| 56 | `get_gist` | Get a gist with file contents |
| 57 | `delete_gist` | Delete a gist |

</details>

<details>
<summary><strong>⚡ GitHub Actions (5 tools)</strong></summary>

| # | Tool | Description |
|---|------|-------------|
| 58 | `list_workflows` | List workflows in a repo |
| 59 | `trigger_workflow` | Trigger a workflow dispatch event |
| 60 | `list_workflow_runs` | List workflow runs (filter by status) |
| 61 | `cancel_workflow_run` | Cancel a running workflow |
| 62 | `rerun_workflow` | Re-run a workflow |

</details>

<details>
<summary><strong>🏢 Organizations & Teams (5 tools)</strong></summary>

| # | Tool | Description |
|---|------|-------------|
| 63 | `list_organizations` | List your orgs |
| 64 | `list_org_members` | List org members |
| 65 | `list_org_repos` | List org repos |
| 66 | `list_teams` | List teams in an org |
| 67 | `list_team_members` | List team members |

</details>

<details>
<summary><strong>🔗 Webhooks (3 tools)</strong></summary>

| # | Tool | Description |
|---|------|-------------|
| 68 | `create_webhook` | Create a repo webhook |
| 69 | `list_webhooks` | List webhooks |
| 70 | `delete_webhook` | Delete a webhook |

</details>

<details>
<summary><strong>👤 User & Social (11 tools)</strong></summary>

| # | Tool | Description |
|---|------|-------------|
| 29 | `get_authenticated_user` | Get your profile |
| 30 | `get_user_profile` | Get any user's public profile |
| 31 | `star_repository` | Star a repo |
| 32 | `unstar_repository` | Unstar a repo |
| 33 | `list_starred_repositories` | List your starred repos |
| 80 | `follow_user` | Follow a user |
| 81 | `unfollow_user` | Unfollow a user |
| 82 | `list_followers` | List followers |
| 83 | `list_following` | List who you follow |
| 84 | `list_user_emails` | List your email addresses |
| 99 | `list_stargazers` | List stargazers of a repo |

</details>

<details>
<summary><strong>🔔 Notifications (2 tools)</strong></summary>

| # | Tool | Description |
|---|------|-------------|
| 71 | `list_notifications` | List notifications |
| 72 | `mark_notifications_read` | Mark all notifications as read |

</details>

<details>
<summary><strong>🔑 Keys (7 tools)</strong></summary>

| # | Tool | Description |
|---|------|-------------|
| 73 | `list_deploy_keys` | List deploy keys |
| 74 | `add_deploy_key` | Add a deploy key |
| 75 | `delete_deploy_key` | Delete a deploy key |
| 76 | `list_ssh_keys` | List SSH keys |
| 77 | `add_ssh_key` | Add an SSH key |
| 78 | `list_gpg_keys` | List GPG keys |
| 79 | `add_gpg_key` | Add a GPG key |

</details>

<details>
<summary><strong>🚀 Deployments & Environments (3 tools)</strong></summary>

| # | Tool | Description |
|---|------|-------------|
| 102 | `list_deployments` | List deployments |
| 103 | `create_deployment_status` | Create deployment status |
| 104 | `list_environments` | List deployment environments |

</details>

<details>
<summary><strong>📦 Packages, Codespaces, Projects & More (6 tools)</strong></summary>

| # | Tool | Description |
|---|------|-------------|
| 87 | `list_repo_projects` | List classic projects |
| 88 | `get_rate_limit` | Check API rate limit |
| 89 | `list_packages` | List packages (npm, docker, etc.) |
| 90 | `delete_package` | Delete a package |
| 91 | `list_codespaces` | List codespaces |
| 101 | `list_security_advisories` | List security advisories |

</details>

---

## 🚀 Quick Start

### Prerequisites

- **Node.js** ≥ 20  
- **Python** ≥ 3.12  
- **MongoDB** (Atlas or local)  
- **Redis** (local or cloud)  
- **Qdrant** (cloud — [qdrant.io](https://cloud.qdrant.io))  
- **OpenAI API Key**  
- **Telegram Bot Token** (from [@BotFather](https://t.me/BotFather))  
- **GitHub Personal Access Token** (per-user, added on dashboard)  

### 1️⃣ Clone

```bash
git clone https://github.com/sandipto729/github_whatsapp.git
cd github_whatsapp
```

### 2️⃣ MCP Server Setup

```bash
cd mcp_server
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

Create `mcp_server/.env`:

```env
OPENAI_API_KEY=sk-...
GITHUB_TOKEN=ghp_...           # Default/fallback token
QDRANT_URL=https://xxx.qdrant.io
QDRANT_API_KEY=your_qdrant_key
```

Run:

```bash
uvicorn index:app --reload --port 8000
```

### 3️⃣ Web Service Setup

```bash
cd web_service
npm install
```

Create `web_service/.env`:

```env
MONGODB_URI=mongodb+srv://...
REDIS_URL=redis://localhost:6379
NEXTAUTH_SECRET=some-random-secret
NEXTAUTH_URL=http://localhost:3000
MCP_SERVER_URL=http://localhost:8000
TELEGRAM_BOT_TOKEN=123456:ABC-...
NEXT_PUBLIC_APP_URL=http://localhost:3000
```

Run:

```bash
npm run dev
```

### 4️⃣ Set Telegram Webhook

```
GET http://localhost:3000/api/telegram/setup?url=https://your-public-url.com
```

---

## 🐳 Docker Compose

```bash
# Create .env.docker files for both services (see above)
docker compose up --build -d
```

Services:
- **web_service** → `http://localhost:3040`  
- **mcp_server** → internal only (port 8000, not exposed)

---

## 💬 Telegram Commands

| Command | Description |
|---------|-------------|
| `/start` | Welcome message + registration link |
| `/link <username> <password>` | Link Telegram to your web account |
| `/me` | Show your profile info |
| `/clear` | Clear conversation history |
| `/help` | List all commands |
| *any text* | Chat with the GitHub AI agent |

### Example Conversations

```
You: Create a private repo called "my-api" with a README
Bot: ✅ Created private repo sandipto729/my-api with README

You: Create a branch "feature/auth" on my-api
Bot: ✅ Created branch feature/auth from main

You: Push a file src/main.py with a hello world script
Bot: ✅ Pushed src/main.py to feature/auth

You: Create a PR to merge feature/auth into main
Bot: ✅ Created PR #1 "Merge feature/auth into main"

You: List my open issues on my-api
Bot: No open issues found on sandipto729/my-api

You: Trigger the CI workflow on my-api
Bot: ✅ Triggered workflow ci.yml on branch main
```

---

## 🧠 Memory System

| Layer | Storage | Scope | TTL |
|-------|---------|-------|-----|
| **Short-term** | Redis | Last 5 exchanges (10 messages) | 1 hour |
| **Long-term** | Mem0 → Qdrant | Semantic memories per user | Permanent |

The agent searches long-term memory before every response and saves each exchange after responding, giving it persistent context across sessions.

---

## 📂 Project Structure

```
github_whatsapp/
├── docker-compose.yml
├── README.md
│
├── mcp_server/                    # Python — AI Agent + MCP Server
│   ├── Dockerfile
│   ├── index.py                   # FastAPI entry point (/chat endpoint)
│   ├── requirements.txt
│   ├── chat/
│   │   ├── agent.py               # OpenAI Agents SDK agent definition
│   │   └── long_memory.py         # Mem0 + Qdrant long-term memory
│   └── github_mcp/
│       └── mcp_github.py          # FastMCP server — 104 GitHub tools
│
└── web_service/                   # Next.js — Web UI + Telegram Webhook
    ├── Dockerfile
    ├── package.json
    ├── app/
    │   ├── page.js                # Login / Register page
    │   ├── layout.js              # Root layout
    │   ├── providers.js           # NextAuth SessionProvider
    │   ├── globals.css            # Tailwind styles
    │   ├── dashboard/
    │   │   └── page.js            # User dashboard (token, phone, profile)
    │   ├── chat/
    │   │   └── page.js            # Web chat interface
    │   ├── api/
    │   │   ├── auth/
    │   │   │   ├── [...nextauth]/route.js   # NextAuth handler
    │   │   │   └── register/route.js        # Registration endpoint
    │   │   ├── chat/route.js                # Web chat → MCP proxy
    │   │   ├── telegram/route.js            # Telegram webhook handler
    │   │   ├── telegram/setup/route.js      # Set Telegram webhook URL
    │   │   └── user/route.js                # User profile CRUD
    │   └── lib/
    │       ├── auth.js            # NextAuth config (credentials)
    │       ├── db.js              # MongoDB connection
    │       ├── memory.js          # Redis short-term history
    │       ├── redis.js           # Redis client
    │       ├── telegram.js        # Telegram API helpers
    │       └── models/
    │           └── User.js        # Mongoose User model
    └── public/
```

---

## 🔑 GitHub Scopes Covered

The 104 tools map to these GitHub OAuth / PAT scopes:

| Scope | What It Enables |
|-------|-----------------|
| `repo` | Full repo control — CRUD, branches, files, PRs, issues, collaborators |
| `repo:status` | Read/create commit statuses, check runs |
| `repo_deployment` | Deployments, deployment statuses, environments |
| `repo:invite` | Repository invitations |
| `security_events` | Security advisories |
| `workflow` | GitHub Actions — list, trigger, cancel, re-run workflows |
| `write:packages` / `read:packages` / `delete:packages` | Package management |
| `admin:org` / `read:org` | Organizations, teams, members |
| `admin:repo_hook` | Webhooks — create, list, delete |
| `admin:public_key` | SSH keys, deploy keys |
| `admin:gpg_key` | GPG keys |
| `gist` | Create, list, read, delete gists |
| `notifications` | List, mark-as-read notifications |
| `user` / `read:user` | User profile |
| `user:email` | Email addresses |
| `user:follow` | Follow/unfollow users |
| `delete_repo` | Delete repositories |
| `project` / `read:project` | Classic projects |
| `codespace` | List codespaces |

---

## 📄 License

MIT

---

## 🙏 Credits

- [OpenAI Agents SDK](https://github.com/openai/openai-agents-python)  
- [FastMCP](https://github.com/jlowin/fastmcp)  
- [Mem0](https://github.com/mem0ai/mem0)  
- [Next.js](https://nextjs.org)  
- [NextAuth.js](https://next-auth.js.org)