#!/usr/bin/env python3
"""
OpenClaw-inspired Telegram Bot for SetRise3 Repository Management
Production-grade AI Agent using DeepSeek
Compatible with Python 3.13+ (uses httpx + getUpdates)
"""

import os
import sys
import json
import time
import logging
import asyncio
import re
from typing import Dict, Optional
from datetime import datetime

import httpx
from github import Github, GithubException

# -------------------- Configuration --------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("setrize-bot")

# Environment variables (set in Railway)
TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
DEEPSEEK_API_KEY = os.environ["DEEPSEEK_API_KEY"]
GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]
GITHUB_REPO = "rkm2004europe/setrise3"   # target repository

DEEPSEEK_MODEL = "deepseek-chat"
MAX_TOKENS = 4000
TEMPERATURE = 0.3

# GitHub client
g = Github(GITHUB_TOKEN)
repo = g.get_repo(GITHUB_REPO)

# In-memory session storage per user
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

Project structure (SetRize3):
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

# -------------------- Helper Functions --------------------
async def deepseek_chat(messages: list, user_id: Optional[int] = None) -> str:
    """Send chat request to DeepSeek with session context."""
    try:
        full_messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        if user_id and user_id in user_sessions:
            full_messages.extend(user_sessions[user_id][-10:])  # last 10 messages
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
        logger.error(f"DeepSeek API error: {e}")
        return f"❌ Error contacting DeepSeek: {str(e)}"

async def telegram_api(method: str, payload: dict) -> dict:
    """Make a generic Telegram Bot API call."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/{method}",
            json=payload,
        )
        return r.json()

async def send_message(chat_id: int, text: str, parse_mode: str = "Markdown"):
    """Send a message to a chat."""
    return await telegram_api("sendMessage", {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
    })

async def download_file(file_id: str) -> bytes:
    """Download a file from Telegram."""
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getFile?file_id={file_id}"
        )
        path = r.json()["result"]["file_path"]
        r2 = await client.get(
            f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{path}"
        )
        return r2.content

def get_file_from_github(file_path: str) -> Optional[str]:
    """Read a file's content from the GitHub repository."""
    try:
        content = repo.get_contents(file_path)
        return content.decoded_content.decode("utf-8")
    except:
        return None

def create_github_file(file_path: str, content: str, commit_msg: str) -> str:
    """Create a new file on GitHub."""
    try:
        existing = repo.get_contents(file_path)
        return f"⚠️ File `{file_path}` already exists. Use /edit to modify it."
    except:
        repo.create_file(file_path, commit_msg, content)
        return f"✅ Created: `{file_path}`"

def update_github_file(file_path: str, content: str, commit_msg: str) -> str:
    """Update an existing file on GitHub."""
    try:
        existing = repo.get_contents(file_path)
        repo.update_file(file_path, commit_msg, content, existing.sha)
        return f"✅ Updated: `{file_path}`"
    except GithubException as e:
        if e.status == 404:
            return create_github_file(file_path, content, commit_msg)
        return f"❌ Error updating file: {str(e)}"

def get_repo_structure(path: str = "lib", prefix: str = "") -> str:
    """Recursively retrieve the repository directory tree."""
    try:
        contents = repo.get_contents(path)
        result = []
        for item in contents:
            if item.type == "dir":
                result.append(f"{prefix}📁 {item.name}/")
                result.append(get_repo_structure(item.path, prefix + "  "))
            else:
                result.append(f"{prefix}📄 {item.name}")
        return "\n".join(result)
    except:
        return ""

def read_memory() -> str:
    """Read the MEMORY.md file from the repository."""
    content = get_file_from_github(MEMORY_FILE)
    return content if content else ""

def write_memory(content: str) -> bool:
    """Overwrite the MEMORY.md file."""
    try:
        update_github_file(MEMORY_FILE, content, "📝 Update memory")
        return True
    except:
        return False

def add_to_memory(note: str) -> str:
    """Append a timestamped note to MEMORY.md."""
    current = read_memory()
    timestamp = datetime.now().isoformat()
    new_entry = f"\n### {timestamp}\n{note}\n"
    updated = (current + new_entry) if current else f"# 🧠 SetRize3 Memory\n{new_entry}"
    if write_memory(updated):
        return "✅ Note saved to memory."
    return "❌ Failed to save to memory."

# -------------------- Update Processor --------------------
async def process_update(update: dict):
    """Process a single Telegram update (message, command, document)."""
    message = update.get("message")
    if not message:
        return

    chat_id = message.get("chat", {}).get("id")
    text = message.get("text", "")
    document = message.get("document")
    user_id = message.get("from", {}).get("id")

    # Handle /start
    if text == "/start":
        await send_message(chat_id,
            "🤖 *Welcome! I'm the SetRize3 AI Assistant (OpenClaw-style).*\n\n"
            "📄 Send a `.dart` file → I'll place it in the correct path.\n"
            "💬 Ask any question about the project.\n"
            "📁 `/structure` → Show project structure.\n"
            "🧠 `/memory <note>` → Save a note to project memory.\n"
            "🔍 `/review <file or description>` → Analyze code.\n"
            "✏️ `/edit <path> <description>` → Edit a file.\n"
            "🔀 `/pr` → Create a Pull Request (under development)."
        )

    # Handle /structure
    elif text == "/structure":
        await send_message(chat_id, "⏳ Reading project structure...")
        structure = get_repo_structure()
        if structure:
            await send_message(chat_id, f"📁 *Project Structure:*\n```\n{structure}\n```")
        else:
            await send_message(chat_id, "❌ Could not read repository structure.")

    # Handle /memory
    elif text.startswith("/memory"):
        note = text[len("/memory"):].strip()
        if not note:
            mem = read_memory()
            if mem:
                await send_message(chat_id, f"🧠 *Memory:*\n{mem[:3000]}")
            else:
                await send_message(chat_id, "🧠 Memory is empty. Add a note: `/memory <text>`")
        else:
            result = add_to_memory(note)
            await send_message(chat_id, result)

    # Handle /review
    elif text.startswith("/review"):
        target = text[len("/review"):].strip()
        if not target:
            await send_message(chat_id, "Usage: `/review <file_path or description>`")
            return
        await send_message(chat_id, "🔍 Analyzing...")
        # If it looks like a file path, fetch its content
        code = None
        if "/" in target:
            code = get_file_from_github(target)
        prompt = f"Review this code:\n```dart\n{code[:3000]}\n```" if code else f"Review this aspect of SetRize3: {target}"
        response = await deepseek_chat([{"role": "user", "content": prompt}], user_id)
        await send_message(chat_id, response)

    # Handle /edit
    elif text.startswith("/edit"):
        parts = text[len("/edit"):].strip().split(maxsplit=1)
        if len(parts) < 2:
            await send_message(chat_id, "Usage: `/edit <path> <description of change>`")
            return
        file_path, description = parts[0], parts[1]
        current = get_file_from_github(file_path)
        if not current:
            await send_message(chat_id, f"❌ File `{file_path}` not found.")
            return
        await send_message(chat_id, "✏️ Editing file...")
        prompt = f"Edit the file `{file_path}` as follows: {description}\n\nCurrent content:\n```dart\n{current[:3000]}\n```\nReturn the full modified code."
        response = await deepseek_chat([{"role": "user", "content": prompt}], user_id)
        # Extract code from response (simple heuristic)
        code_match = re.search(r"```dart\n(.*?)```", response, re.DOTALL)
        new_code = code_match.group(1) if code_match else response
        result = update_github_file(file_path, new_code, f"✏️ Edit {file_path}: {description}")
        await send_message(chat_id, f"{result}\n\n{response[:2000]}")

    # Handle /pr (placeholder)
    elif text.startswith("/pr"):
        await send_message(chat_id, "🔀 Pull Request feature is coming soon. For now, use /edit and create a PR manually.")

    # Handle document (.dart file)
    elif document:
        file_name = document.get("file_name", "")
        if not file_name.endswith(".dart"):
            await send_message(chat_id, "⚠️ Please send only `.dart` files.")
            return
        await send_message(chat_id, "⏳ Analyzing file and determining correct path...")
        try:
            file_bytes = await download_file(document["file_id"])
            content = file_bytes.decode("utf-8")
            # Ask DeepSeek for the correct path
            ai_response = await deepseek_chat([{
                "role": "user",
                "content": f"File name: {file_name}\n\nContent:\n```dart\n{content[:2000]}\n```\nDetermine the correct path in the SetRize3 project following Clean Architecture. Reply with:\nPath: path/to/file.dart\nReason: brief explanation"
            }], user_id)
            # Parse path and reason
            lines = ai_response.split("\n")
            file_path = ""
            reason = ""
            for line in lines:
                if line.startswith("Path:"):
                    file_path = line.replace("Path:", "").strip()
                elif line.startswith("Reason:"):
                    reason = line.replace("Reason:", "").strip()
            if not file_path:
                await send_message(chat_id, "❌ Could not determine the file path.")
                return
            commit_msg = f"feat: add {file_name} via SetRize Bot"
            result = create_github_file(file_path, content, commit_msg)
            await send_message(chat_id, f"{result}\n📍 Path: `{file_path}`\n💡 {reason}")
            # Update session
            if user_id not in user_sessions:
                user_sessions[user_id] = []
            user_sessions[user_id].append({"role": "assistant", "content": ai_response})
        except Exception as e:
            logger.error(f"Document handling error: {e}")
            await send_message(chat_id, f"❌ Error: {str(e)}")

    # Handle plain text (question/chat)
    elif text and not text.startswith("/"):
        await send_message(chat_id, "⏳ Thinking...")
        # Include memory snippet if available
        memory_snippet = ""
        mem = read_memory()
        if mem:
            memory_snippet = f"\n\nRecent project memory:\n{mem[:1000]}"
        response = await deepseek_chat([{"role": "user", "content": f"{text}{memory_snippet}"}], user_id)
        # Telegram has a 4096 char limit, split if necessary
        if len(response) > 4000:
            parts = [response[i:i+4000] for i in range(0, len(response), 4000)]
            for i, part in enumerate(parts):
                if i == 0:
                    await send_message(chat_id, part)
                else:
                    await send_message(chat_id, part)
        else:
            await send_message(chat_id, response)
        # Update session
        if user_id not in user_sessions:
            user_sessions[user_id] = []
        user_sessions[user_id].append({"role": "user", "content": text})
        user_sessions[user_id].append({"role": "assistant", "content": response})

# -------------------- Main Polling Loop --------------------
async def main():
    logger.info("🤖 SetRize Bot (OpenClaw style) starting...")
    offset = 0
    async with httpx.AsyncClient() as client:
        while True:
            try:
                # Long-polling: wait up to 30 seconds for new updates
                r = await client.get(
                    f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates",
                    params={"offset": offset, "timeout": 30},
                    timeout=35,
                )
                data = r.json()
                if not data.get("ok"):
                    logger.error(f"Telegram API error: {data}")
                    await asyncio.sleep(5)
                    continue
                updates = data.get("result", [])
                for update in updates:
                    offset = update["update_id"] + 1
                    asyncio.create_task(process_update(update))
            except Exception as e:
                logger.error(f"Polling error: {e}")
                await asyncio.sleep(3)

if __name__ == "__main__":
    asyncio.run(main())
