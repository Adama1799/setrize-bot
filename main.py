#!/usr/bin/env python3
"""
SetRize3 AI Bot - OpenClaw Style
DeepSeek + Telegram + GitHub
Python 3.13 compatible (pure httpx, no python-telegram-bot)
"""

import os
import logging
import asyncio
import re
from typing import Dict, Optional
from datetime import datetime

import httpx
from github import Github, GithubException

# -------------------- Logging --------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("setrize-bot")

# -------------------- Config --------------------
TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
DEEPSEEK_API_KEY = os.environ["DEEPSEEK_API_KEY"]
GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]
GITHUB_REPO = os.environ.get("GITHUB_REPO", "rkm2004europe/setrise3")

DEEPSEEK_MODEL = "deepseek-chat"
MAX_TOKENS = 4000
TEMPERATURE = 0.3

# -------------------- GitHub --------------------
g = Github(GITHUB_TOKEN)
repo = g.get_repo(GITHUB_REPO)

# -------------------- In-memory session --------------------
user_sessions: Dict[int, list] = {}
MEMORY_FILE = "MEMORY.md"

# -------------------- System Prompt --------------------
SYSTEM_PROMPT = """You are an advanced AI assistant managing the SetRize3 project – a Flutter application using Clean Architecture.
You are part of an OpenClaw-like Agent Runtime. Your capabilities:
- Analyze code and determine its correct location in the project
- Modify files based on a description
- Suggest architectural improvements
- Create professional Pull Requests
- Answer questions about the project
- Store and retrieve user preferences and notes (memory)

Project structure (SetRise3):
lib/
├── main.dart
├── core/          # Core functionality (theme, routes, DI)
├── features/      # Feature modules
│   ├── auth/      # Authentication
│   ├── home/      # Home screen
│   ├── settings/  # Settings
│   └── ...
├── shared/        # Shared widgets, utilities
└── l10n/          # Localization

When adding a new Dart file, strictly follow Clean Architecture:
- data/datasources/
- data/repositories/
- domain/entities/
- domain/repositories/
- domain/usecases/
- presentation/providers/
- presentation/screens/
- presentation/widgets/

Always respond in concise, professional English. Provide accurate and helpful guidance."""

# -------------------- DeepSeek --------------------
async def deepseek_chat(messages: list, user_id: Optional[int] = None) -> str:
    try:
        full_messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        if user_id and user_id in user_sessions:
            full_messages.extend(user_sessions[user_id][-10:])
        full_messages.extend(messages)

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                "https://api.deepseek.com/chat/completions",
                headers={
                    "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": DEEPSEEK_MODEL,
                    "messages": full_messages,
                    "max_tokens": MAX_TOKENS,
                    "temperature": TEMPERATURE,
                },
            )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]
    except Exception as e:
        logger.error(f"DeepSeek error: {e}")
        return f"❌ Error contacting DeepSeek: {str(e)}"

# -------------------- Telegram Helpers --------------------
async def telegram_api(method: str, payload: dict) -> dict:
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/{method}",
            json=payload,
        )
        return r.json()

async def send_message(chat_id: int, text: str, parse_mode: str = "Markdown"):
    # Telegram limit is 4096 chars
    if len(text) > 4000:
        chunks = [text[i:i+4000] for i in range(0, len(text), 4000)]
        for chunk in chunks:
            await telegram_api("sendMessage", {
                "chat_id": chat_id,
                "text": chunk,
                "parse_mode": parse_mode,
            })
            await asyncio.sleep(0.3)
    else:
        await telegram_api("sendMessage", {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode,
        })

async def send_typing(chat_id: int):
    await telegram_api("sendChatAction", {"chat_id": chat_id, "action": "typing"})

async def download_file(file_id: str) -> bytes:
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

# -------------------- GitHub Helpers --------------------
def get_file_from_github(file_path: str) -> Optional[str]:
    try:
        content = repo.get_contents(file_path)
        return content.decoded_content.decode("utf-8")
    except Exception:
        return None

def create_github_file(file_path: str, content: str, commit_msg: str) -> str:
    try:
        repo.get_contents(file_path)
        return f"⚠️ File `{file_path}` already exists. Use /edit to modify it."
    except GithubException:
        repo.create_file(file_path, commit_msg, content)
        return f"✅ Created: `{file_path}`"

def update_github_file(file_path: str, content: str, commit_msg: str) -> str:
    try:
        existing = repo.get_contents(file_path)
        repo.update_file(file_path, commit_msg, content, existing.sha)
        return f"✅ Updated: `{file_path}`"
    except GithubException as e:
        if e.status == 404:
            return create_github_file(file_path, content, commit_msg)
        return f"❌ GitHub error: {str(e)}"

def get_repo_structure(path: str = "lib", prefix: str = "", depth: int = 0) -> str:
    if depth > 4:
        return ""
    try:
        contents = repo.get_contents(path)
        result = []
        for item in sorted(contents, key=lambda x: (x.type != "dir", x.name)):
            if item.type == "dir":
                result.append(f"{prefix}📁 {item.name}/")
                sub = get_repo_structure(item.path, prefix + "  ", depth + 1)
                if sub:
                    result.append(sub)
            else:
                result.append(f"{prefix}📄 {item.name}")
        return "\n".join(result)
    except Exception:
        return ""

# -------------------- Memory --------------------
def read_memory() -> str:
    content = get_file_from_github(MEMORY_FILE)
    return content if content else ""

def write_memory(content: str) -> bool:
    try:
        update_github_file(MEMORY_FILE, content, "📝 Update memory")
        return True
    except Exception:
        return False

def add_to_memory(note: str) -> str:
    current = read_memory()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    new_entry = f"\n### {timestamp}\n{note}\n"
    updated = (current + new_entry) if current else f"# 🧠 SetRize3 Memory\n{new_entry}"
    return "✅ Note saved to memory." if write_memory(updated) else "❌ Failed to save to memory."

# -------------------- Command Handlers --------------------
async def handle_start(chat_id: int):
    await send_message(chat_id,
        "🤖 *SetRize3 AI Bot* (OpenClaw Style)\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "📄 Send a `.dart` file → auto-place in correct path\n"
        "💬 Ask anything about the project\n\n"
        "*Commands:*\n"
        "📁 `/structure` — Show project structure\n"
        "🧠 `/memory <note>` — Save/read memory\n"
        "🔍 `/review <path or topic>` — Code review\n"
        "✏️ `/edit <path> <description>` — Edit a file\n"
        "📊 `/status` — Bot status\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "_Powered by DeepSeek + GitHub_"
    )

async def handle_structure(chat_id: int):
    await send_typing(chat_id)
    await send_message(chat_id, "⏳ Reading repository structure...")
    structure = get_repo_structure()
    if structure:
        await send_message(chat_id, f"📁 *Project Structure (`lib/`):*\n```\n{structure[:3500]}\n```")
    else:
        await send_message(chat_id, "❌ Could not read repository structure. Check GitHub token permissions.")

async def handle_memory(chat_id: int, user_id: int, note: str):
    await send_typing(chat_id)
    if not note:
        mem = read_memory()
        if mem:
            await send_message(chat_id, f"🧠 *Project Memory:*\n\n{mem[:3000]}")
        else:
            await send_message(chat_id, "🧠 Memory is empty.\nAdd a note: `/memory <your text>`")
    else:
        result = add_to_memory(note)
        await send_message(chat_id, result)

async def handle_review(chat_id: int, user_id: int, target: str):
    if not target:
        await send_message(chat_id, "Usage: `/review <file_path or topic>`\nExample: `/review lib/main.dart`")
        return
    await send_typing(chat_id)
    await send_message(chat_id, "🔍 Analyzing...")
    code = None
    if "/" in target and target.endswith(".dart"):
        code = get_file_from_github(target)
    if code:
        prompt = f"Please review this Dart file from SetRize3:\n\nFile: `{target}`\n```dart\n{code[:3000]}\n```\n\nProvide: 1) Code quality assessment 2) Architectural compliance 3) Specific improvements"
    else:
        prompt = f"Please review/analyze this aspect of the SetRize3 Flutter project: {target}"
    response = await deepseek_chat([{"role": "user", "content": prompt}], user_id)
    await send_message(chat_id, response)

async def handle_edit(chat_id: int, user_id: int, args: str):
    parts = args.strip().split(maxsplit=1)
    if len(parts) < 2:
        await send_message(chat_id, "Usage: `/edit <file_path> <description of change>`\nExample: `/edit lib/main.dart Add dark mode support`")
        return
    file_path, description = parts[0], parts[1]
    current = get_file_from_github(file_path)
    if not current:
        await send_message(chat_id, f"❌ File `{file_path}` not found in repository.")
        return
    await send_typing(chat_id)
    await send_message(chat_id, f"✏️ Editing `{file_path}`...")
    prompt = (
        f"Modify the file `{file_path}` as follows: {description}\n\n"
        f"Current content:\n```dart\n{current[:3000]}\n```\n\n"
        "Return ONLY the complete modified Dart code inside a ```dart code block. No explanations before the code block."
    )
    response = await deepseek_chat([{"role": "user", "content": prompt}], user_id)
    code_match = re.search(r"```dart\n(.*?)```", response, re.DOTALL)
    new_code = code_match.group(1).strip() if code_match else response.strip()
    result = update_github_file(file_path, new_code, f"✏️ {description[:72]}")
    summary = response[:1500] if len(response) > 1500 else response
    await send_message(chat_id, f"{result}\n\n💡 *AI Notes:*\n{summary}")

async def handle_status(chat_id: int):
    await send_typing(chat_id)
    try:
        r = repo.get_git_ref("heads/main")
        sha = r.object.sha[:7]
        status = f"✅ *Bot Status*\n\n🔗 Repo: `{GITHUB_REPO}`\n📌 HEAD: `{sha}`\n🤖 Model: `{DEEPSEEK_MODEL}`\n⏰ Time: `{datetime.now().strftime('%Y-%m-%d %H:%M UTC')}`"
    except Exception as e:
        status = f"⚠️ *Bot Status*\n\n🔗 Repo: `{GITHUB_REPO}`\n❌ GitHub: {str(e)}\n🤖 Model: `{DEEPSEEK_MODEL}`"
    await send_message(chat_id, status)

async def handle_document(chat_id: int, user_id: int, document: dict):
    file_name = document.get("file_name", "")
    if not file_name.endswith(".dart"):
        await send_message(chat_id, "⚠️ Please send only `.dart` files.")
        return
    await send_typing(chat_id)
    await send_message(chat_id, f"⏳ Analyzing `{file_name}`...")
    try:
        file_bytes = await download_file(document["file_id"])
        content = file_bytes.decode("utf-8")
        ai_response = await deepseek_chat([{
            "role": "user",
            "content": (
                f"File name: `{file_name}`\n\n"
                f"Content:\n```dart\n{content[:2500]}\n```\n\n"
                "Determine the correct path in SetRize3 following Clean Architecture.\n"
                "Reply with EXACTLY this format (no extra text):\n"
                "Path: lib/features/xxx/yyy/file_name.dart\n"
                "Reason: one sentence explanation"
            )
        }], user_id)

        file_path = ""
        reason = ""
        for line in ai_response.split("\n"):
            if line.startswith("Path:"):
                file_path = line.replace("Path:", "").strip()
            elif line.startswith("Reason:"):
                reason = line.replace("Reason:", "").strip()

        if not file_path:
            await send_message(chat_id, f"❌ Could not determine path.\n\nAI response:\n{ai_response[:1000]}")
            return

        commit_msg = f"feat: add {file_name} via SetRize Bot"
        result = create_github_file(file_path, content, commit_msg)
        await send_message(chat_id,
            f"{result}\n"
            f"📍 Path: `{file_path}`\n"
            f"💡 {reason}"
        )
        user_sessions.setdefault(user_id, []).append({"role": "assistant", "content": ai_response})
    except Exception as e:
        logger.error(f"Document error: {e}")
        await send_message(chat_id, f"❌ Error processing file: {str(e)}")

async def handle_text(chat_id: int, user_id: int, text: str):
    await send_typing(chat_id)
    mem = read_memory()
    memory_snippet = f"\n\n[Project memory context]:\n{mem[:800]}" if mem else ""
    response = await deepseek_chat(
        [{"role": "user", "content": f"{text}{memory_snippet}"}],
        user_id
    )
    await send_message(chat_id, response)
    user_sessions.setdefault(user_id, []).extend([
        {"role": "user", "content": text},
        {"role": "assistant", "content": response},
    ])
    # Keep session manageable
    if len(user_sessions[user_id]) > 20:
        user_sessions[user_id] = user_sessions[user_id][-20:]

# -------------------- Update Router --------------------
async def process_update(update: dict):
    message = update.get("message")
    if not message:
        return

    chat_id: int = message.get("chat", {}).get("id")
    user_id: int = message.get("from", {}).get("id")
    text: str = message.get("text", "") or ""
    document: Optional[dict] = message.get("document")

    try:
        if text == "/start":
            await handle_start(chat_id)
        elif text == "/structure":
            await handle_structure(chat_id)
        elif text.startswith("/memory"):
            await handle_memory(chat_id, user_id, text[len("/memory"):].strip())
        elif text.startswith("/review"):
            await handle_review(chat_id, user_id, text[len("/review"):].strip())
        elif text.startswith("/edit"):
            await handle_edit(chat_id, user_id, text[len("/edit"):].strip())
        elif text in ("/status", "/ping"):
            await handle_status(chat_id)
        elif text.startswith("/pr"):
            await send_message(chat_id, "🔀 Pull Request feature coming soon. Stay tuned!")
        elif document:
            await handle_document(chat_id, user_id, document)
        elif text and not text.startswith("/"):
            await handle_text(chat_id, user_id, text)
    except Exception as e:
        logger.error(f"Error processing update: {e}")
        try:
            await send_message(chat_id, f"❌ Unexpected error: {str(e)}")
        except Exception:
            pass

# -------------------- Polling Loop --------------------
async def main():
    logger.info("🤖 SetRize Bot starting (OpenClaw style, Python 3.13 compatible)...")
    logger.info(f"📦 Repo: {GITHUB_REPO}")
    offset = 0

    async with httpx.AsyncClient() as client:
        while True:
            try:
                r = await client.get(
                    f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates",
                    params={"offset": offset, "timeout": 30, "allowed_updates": ["message"]},
                    timeout=35.0,
                )
                data = r.json()
                if not data.get("ok"):
                    logger.error(f"Telegram API error: {data}")
                    await asyncio.sleep(5)
                    continue

                for update in data.get("result", []):
                    offset = update["update_id"] + 1
                    asyncio.create_task(process_update(update))

            except httpx.TimeoutException:
                # Normal for long-polling
                pass
            except Exception as e:
                logger.error(f"Polling error: {e}")
                await asyncio.sleep(3)

if __name__ == "__main__":
    asyncio.run(main())
