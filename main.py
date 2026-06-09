#!/usr/bin/env python3
"""
SetRize3 AI Agent – OpenClaw-inspired Telegram Bot
English version – production ready, Python 3.13 compatible.
Uses: httpx (Telegram API + DeepSeek) and PyGithub.
No python-telegram-bot dependency.
"""

import os
import logging
import asyncio
import re
from typing import Dict, Optional
from datetime import datetime

import httpx
from github import Github, GithubException

# ---------- Logging ----------
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("setrize-agent")

# ---------- Configuration ----------
TELEGRAM_TOKEN   = os.environ["TELEGRAM_TOKEN"]
DEEPSEEK_API_KEY = os.environ["DEEPSEEK_API_KEY"]
GITHUB_TOKEN     = os.environ["GITHUB_TOKEN"]
GITHUB_REPO      = os.environ.get("GITHUB_REPO", "rkm2004europe/setrise3")

DEEPSEEK_MODEL = "deepseek-chat"
MAX_TOKENS     = 4000
TEMPERATURE    = 0.3

# ---------- GitHub client ----------
g    = Github(GITHUB_TOKEN)
repo = g.get_repo(GITHUB_REPO)

# ---------- In-memory sessions ----------
user_sessions: Dict[int, list] = {}
MEMORY_FILE = "MEMORY.md"

# ---------- System prompt ----------
SYSTEM_PROMPT = """You are SetRize Agent – an AI assistant managing the SetRize3 Flutter project.
You strictly follow Clean Architecture.

Project layout:
lib/
├── main.dart
├── core/          # Theme, routes, DI
├── features/      # Feature modules (auth, home, settings, ...)
├── shared/        # Shared widgets and utilities
└── l10n/          # Localization

Clean Architecture layers inside a feature:
- data/datasources/
- data/repositories/
- domain/entities/
- domain/repositories/
- domain/usecases/
- presentation/providers/
- presentation/screens/
- presentation/widgets/

When you receive a Dart file, you MUST reply in this exact format:
Path: lib/features/<feature>/<layer>/<filename.dart>
Reason: one‑sentence explanation why this location is correct.

Always answer in clear, professional English. Keep answers concise."""

# ---------- DeepSeek API ----------
async def deepseek_chat(messages: list, user_id: Optional[int] = None) -> str:
    """Call DeepSeek with session context (last 10 messages)."""
    full = [{"role": "system", "content": SYSTEM_PROMPT}]
    if user_id and user_id in user_sessions:
        full.extend(user_sessions[user_id][-10:])
    full.extend(messages)

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            "https://api.deepseek.com/chat/completions",
            headers={
                "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": DEEPSEEK_MODEL,
                "messages": full,
                "max_tokens": MAX_TOKENS,
                "temperature": TEMPERATURE,
            },
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]

# ---------- Telegram API helpers ----------
async def tg(method: str, payload: dict) -> dict:
    """Send a request to Telegram Bot API."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/{method}",
            json=payload,
        )
        return r.json()

async def send_message(chat_id: int, text: str, parse_mode: str = "Markdown"):
    """Send a message, splitting if longer than 4000 characters."""
    while text:
        chunk, text = text[:4000], text[4000:]
        await tg("sendMessage", {
            "chat_id": chat_id,
            "text": chunk,
            "parse_mode": parse_mode,
        })
        await asyncio.sleep(0.3)

async def send_typing(chat_id: int):
    await tg("sendChatAction", {"chat_id": chat_id, "action": "typing"})

async def download_file(file_id: str) -> bytes:
    """Download a file from Telegram."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.get(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getFile",
            params={"file_id": file_id},
        )
        path = r.json()["result"]["file_path"]
        r2 = await client.get(
            f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{path}"
        )
        return r2.content

# ---------- GitHub helpers ----------
def gh_read(path: str) -> Optional[str]:
    """Read file content from GitHub."""
    try:
        return repo.get_contents(path).decoded_content.decode("utf-8")
    except Exception:
        return None

def gh_create(path: str, content: str, commit_msg: str) -> str:
    """Create a new file on GitHub."""
    try:
        repo.get_contents(path)
        return f"⚠️ File `{path}` already exists. Use /edit to modify."
    except GithubException:
        repo.create_file(path, commit_msg, content)
        return f"✅ Created: `{path}`"

def gh_update(path: str, content: str, commit_msg: str) -> str:
    """Update an existing file (or create if missing)."""
    try:
        f = repo.get_contents(path)
        repo.update_file(path, commit_msg, content, f.sha)
        return f"✅ Updated: `{path}`"
    except GithubException as e:
        if e.status == 404:
            return gh_create(path, content, commit_msg)
        return f"❌ GitHub error: {str(e)}"

def gh_tree(path: str = "lib", prefix: str = "", depth: int = 0) -> str:
    """Return a string representation of the repository tree."""
    if depth > 4:
        return ""
    try:
        items = sorted(repo.get_contents(path),
                       key=lambda x: (x.type != "dir", x.name))
        lines = []
        for item in items:
            if item.type == "dir":
                lines.append(f"{prefix}📁 {item.name}/")
                sub = gh_tree(item.path, prefix + "  ", depth + 1)
                if sub:
                    lines.append(sub)
            else:
                lines.append(f"{prefix}📄 {item.name}")
        return "\n".join(lines)
    except Exception:
        return ""

# ---------- Memory management ----------
def memory_read() -> str:
    return gh_read(MEMORY_FILE) or ""

def memory_add(note: str) -> str:
    current = memory_read()
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    entry = f"\n### {ts}\n{note}\n"
    updated = current + entry if current else f"# 🧠 SetRize3 Memory\n{entry}"
    res = gh_update(MEMORY_FILE, updated, "📝 Update memory")
    return "✅ Note saved." if "✅" in res else "❌ Failed to save."

# ---------- Command handlers ----------
async def cmd_start(chat_id: int):
    await send_message(chat_id,
        "🦞 *SetRize3 AI Agent*\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "📄 Send a `.dart` file → placed automatically.\n"
        "💬 Ask anything about the project.\n\n"
        "*Commands:*\n"
        "📁 `/structure` – show project tree\n"
        "🧠 `/memory <note>` – read / write memory\n"
        "🔍 `/review <path>` – code review\n"
        "✏️ `/edit <path> <desc>` – edit a file\n"
        "📊 `/status` – bot & repo status\n"
        "━━━━━━━━━━━━━━━━━━━━"
    )

async def cmd_structure(chat_id: int):
    await send_typing(chat_id)
    tree = gh_tree()
    if tree:
        await send_message(chat_id, f"📁 *Project structure:*\n```\n{tree[:3500]}\n```")
    else:
        await send_message(chat_id, "❌ Could not read repository structure.")

async def cmd_memory(chat_id: int, note: str):
    await send_typing(chat_id)
    if not note:
        mem = memory_read()
        if mem:
            await send_message(chat_id, f"🧠 *Memory:*\n\n{mem[:3000]}")
        else:
            await send_message(chat_id, "🧠 Memory is empty. Add a note: `/memory <text>`")
    else:
        await send_message(chat_id, memory_add(note))

async def cmd_review(chat_id: int, user_id: int, target: str):
    if not target:
        await send_message(chat_id, "Usage: `/review lib/features/auth/...`")
        return
    await send_typing(chat_id)
    code = gh_read(target) if "/" in target else None
    prompt = (
        f"Review this Dart file:\n```dart\n{code[:3000]}\n```"
        if code else f"Review this aspect of SetRize3: {target}"
    )
    response = await deepseek_chat([{"role": "user", "content": prompt}], user_id)
    await send_message(chat_id, response)

async def cmd_edit(chat_id: int, user_id: int, args: str):
    parts = args.strip().split(maxsplit=1)
    if len(parts) < 2:
        await send_message(chat_id, "Usage: `/edit lib/main.dart description of change`")
        return
    path, desc = parts[0], parts[1]
    current = gh_read(path)
    if not current:
        await send_message(chat_id, f"❌ File `{path}` not found.")
        return
    await send_typing(chat_id)
    prompt = (
        f"Edit the file `{path}` according to: {desc}\n\n"
        f"Current content:\n```dart\n{current[:3000]}\n```\n\n"
        "Return ONLY the full modified code inside a ```dart block."
    )
    response = await deepseek_chat([{"role": "user", "content": prompt}], user_id)
    match = re.search(r"```dart\n(.*?)```", response, re.DOTALL)
    new_code = match.group(1).strip() if match else response.strip()
    result = gh_update(path, new_code, f"✏️ {desc[:72]}")
    await send_message(chat_id, f"{result}\n\n💡 {response[:1000]}")

async def cmd_status(chat_id: int):
    await send_typing(chat_id)
    try:
        sha = repo.get_git_ref("heads/main").object.sha[:7]
        await send_message(chat_id,
            f"✅ *Agent Status*\n\n"
            f"📦 Repo: `{GITHUB_REPO}`\n"
            f"🔗 HEAD: `{sha}`\n"
            f"🧠 Model: `{DEEPSEEK_MODEL}`\n"
            f"⏰ `{datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}`"
        )
    except Exception as e:
        await send_message(chat_id, f"⚠️ Status error: {str(e)}")

async def handle_document(chat_id: int, user_id: int, doc: dict):
    file_name = doc.get("file_name", "")
    if not file_name.endswith(".dart"):
        await send_message(chat_id, "⚠️ Only `.dart` files are accepted.")
        return

    await send_typing(chat_id)
    await send_message(chat_id, f"⏳ Analyzing `{file_name}`...")

    try:
        content = (await download_file(doc["file_id"])).decode("utf-8")
        ai = await deepseek_chat([{
            "role": "user",
            "content": (
                f"File name: {file_name}\n"
                f"Content:\n```dart\n{content[:2500]}\n```\n\n"
                "Reply EXACTLY:\n"
                "Path: lib/features/<feature>/<layer>/<file.dart>\n"
                "Reason: one sentence."
            )
        }], user_id)

        path = ""
        reason = ""
        for line in ai.split("\n"):
            if line.startswith("Path:"):
                path = line[5:].strip()
            elif line.startswith("Reason:"):
                reason = line[7:].strip()

        if not path:
            await send_message(chat_id, f"❌ Could not determine path.\n\n{ai[:500]}")
            return

        result = gh_create(path, content, f"feat: add {file_name} via SetRize Agent")
        await send_message(chat_id, f"{result}\n📍 `{path}`\n💡 {reason}")

    except Exception as e:
        logger.error(f"Document handling error: {e}")
        await send_message(chat_id, f"❌ Error: {str(e)}")

async def handle_text(chat_id: int, user_id: int, text: str):
    await send_typing(chat_id)
    mem = memory_read()
    ctx = f"\n\n[Project memory]:\n{mem[:600]}" if mem else ""
    response = await deepseek_chat(
        [{"role": "user", "content": f"{text}{ctx}"}], user_id
    )
    await send_message(chat_id, response)
    # update session
    if user_id not in user_sessions:
        user_sessions[user_id] = []
    user_sessions[user_id].extend([
        {"role": "user", "content": text},
        {"role": "assistant", "content": response},
    ])
    if len(user_sessions[user_id]) > 20:
        user_sessions[user_id] = user_sessions[user_id][-20:]

# ---------- Main update dispatcher ----------
async def process_update(update: dict):
    msg = update.get("message")
    if not msg:
        return
    chat_id = msg["chat"]["id"]
    user_id = msg["from"]["id"]
    text    = msg.get("text", "") or ""
    doc     = msg.get("document")

    try:
        if   text == "/start":
            await cmd_start(chat_id)
        elif text == "/structure":
            await cmd_structure(chat_id)
        elif text.startswith("/memory"):
            await cmd_memory(chat_id, text[7:].strip())
        elif text.startswith("/review"):
            await cmd_review(chat_id, user_id, text[7:].strip())
        elif text.startswith("/edit"):
            await cmd_edit(chat_id, user_id, text[5:].strip())
        elif text in ("/status", "/ping"):
            await cmd_status(chat_id)
        elif doc:
            await handle_document(chat_id, user_id, doc)
        elif text and not text.startswith("/"):
            await handle_text(chat_id, user_id, text)
    except Exception as e:
        logger.error(f"Handler error: {e}")
        await send_message(chat_id, f"❌ Unexpected error: {str(e)}")

# ---------- Long polling ----------
async def main():
    logger.info("🦞 SetRize Agent starting...")
    logger.info(f"📦 Connected to {GITHUB_REPO}")
    offset = 0
    async with httpx.AsyncClient() as client:
        while True:
            try:
                r = await client.get(
                    f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates",
                    params={"offset": offset, "timeout": 30},
                    timeout=35.0,
                )
                for update in r.json().get("result", []):
                    offset = update["update_id"] + 1
                    asyncio.create_task(process_update(update))
            except httpx.TimeoutException:
                pass
            except Exception as e:
                logger.error(f"Polling error: {e}")
                await asyncio.sleep(3)

if __name__ == "__main__":
    asyncio.run(main())
