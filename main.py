# Force redeploy v2

#!/usr/bin/env python3
"""
SetRize3 AI Assistant – OpenClaw-inspired Telegram Bot
No python-telegram-bot – works on Python 3.13
"""
import os, asyncio, logging, re, httpx
from datetime import datetime
from typing import Dict, Optional
from github import Github, GithubException

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
DEEPSEEK_API_KEY = os.environ["DEEPSEEK_API_KEY"]
GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]
REPO_NAME = "rkm2004europe/setrise3"
MEMORY_FILE = "MEMORY.md"

g = Github(GITHUB_TOKEN)
repo = g.get_repo(REPO_NAME)

user_sessions: Dict[int, list] = {}

SYSTEM_PROMPT = """You are an advanced AI assistant for the SetRize3 Flutter project.
... (same system prompt as before) ..."""

async def deepseek_chat(messages, user_id=None):
    full = [{"role":"system","content":SYSTEM_PROMPT}]
    if user_id and user_id in user_sessions:
        full.extend(user_sessions[user_id][-10:])
    full.extend(messages)
    async with httpx.AsyncClient(timeout=60) as c:
        r = await c.post("https://api.deepseek.com/chat/completions",
            headers={"Authorization":f"Bearer {DEEPSEEK_API_KEY}","Content-Type":"application/json"},
            json={"model":"deepseek-chat","messages":full,"max_tokens":4000,"temperature":0.3})
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]

async def telegram(method, payload):
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/{method}", json=payload)
        return r.json()

async def send_msg(chat, text, parse="Markdown"):
    await telegram("sendMessage", {"chat_id":chat,"text":text,"parse_mode":parse})

async def download_file(file_id):
    async with httpx.AsyncClient() as c:
        r = await c.get(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getFile?file_id={file_id}")
        path = r.json()["result"]["file_path"]
        r2 = await c.get(f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{path}")
        return r2.content

def get_github_file(path):
    try: return repo.get_contents(path).decoded_content.decode()
    except: return None

def create_file(path, content, msg):
    try:
        repo.get_contents(path)
        return f"⚠️ `{path}` exists."
    except:
        repo.create_file(path, msg, content)
        return f"✅ Created `{path}`"

def update_file(path, content, msg):
    try:
        existing = repo.get_contents(path)
        repo.update_file(path, msg, content, existing.sha)
        return f"✅ Updated `{path}`"
    except GithubException as e:
        if e.status==404: return create_file(path, content, msg)
        return f"❌ Error: {e}"

def repo_tree(path="lib", pre=""):
    try:
        items = repo.get_contents(path)
        res = []
        for i in items:
            if i.type=="dir":
                res.append(f"{pre}📁 {i.name}/")
                res.append(repo_tree(i.path, pre+"  "))
            else:
                res.append(f"{pre}📄 {i.name}")
        return "\n".join(res)
    except: return ""

def read_memory(): return get_github_file(MEMORY_FILE) or ""
def write_memory(c): update_file(MEMORY_FILE, c, "📝 Update memory")
def add_memory(note):
    cur = read_memory()
    ts = datetime.now().isoformat()
    entry = f"\n### {ts}\n{note}\n"
    updated = cur + entry if cur else f"# Memory\n{entry}"
    write_memory(updated)
    return "✅ Saved."

async def process_update(update):
    msg = update.get("message")
    if not msg: return
    chat = msg["chat"]["id"]
    text = msg.get("text","")
    doc = msg.get("document")
    uid = msg["from"]["id"]

    if text=="/start":
        await send_msg(chat, "🤖 *Hello!* Send .dart file or commands: /structure, /memory, /review, /edit")
    elif text=="/structure":
        s = repo_tree()
        await send_msg(chat, f"📁 Structure:\n```\n{s}\n```" if s else "Error")
    elif text.startswith("/memory"):
        note = text[8:].strip()
        if note:
            await send_msg(chat, add_memory(note))
        else:
            m = read_memory()
            await send_msg(chat, f"🧠 Memory:\n{m[:3000]}" if m else "Empty.")
    elif text.startswith("/review"):
        target = text[8:].strip()
        if not target: await send_msg(chat, "Usage: /review <path|desc>"); return
        code = get_github_file(target) if "/" in target else None
        prompt = f"Review:\n```dart\n{code[:3000]}\n```" if code else f"Review: {target}"
        resp = await deepseek_chat([{"role":"user","content":prompt}], uid)
        await send_msg(chat, resp)
    elif text.startswith("/edit"):
        parts = text[6:].strip().split(maxsplit=1)
        if len(parts)<2: await send_msg(chat, "Usage: /edit <path> <description>"); return
        path, desc = parts
        cur = get_github_file(path)
        if not cur: await send_msg(chat, "File not found"); return
        await send_msg(chat, "Editing...")
        prompt = f"Edit `{path}`: {desc}\n\nCurrent:\n```dart\n{cur[:3000]}\n```\nReturn full modified code."
        resp = await deepseek_chat([{"role":"user","content":prompt}], uid)
        code_match = re.search(r"```dart\n(.*?)```", resp, re.DOTALL)
        new_code = code_match.group(1) if code_match else resp
        result = update_file(path, new_code, f"✏️ Edit {path}")
        await send_msg(chat, f"{result}\n\n{resp[:2000]}")
    elif doc:
        fname = doc.get("file_name","")
        if not fname.endswith(".dart"): await send_msg(chat, "Only .dart files"); return
        await send_msg(chat, "Analyzing...")
        content = (await download_file(doc["file_id"])).decode()
        ai = await deepseek_chat([{"role":"user","content":f"File: {fname}\n```dart\n{content[:2000]}\n```\nPath:"}], uid)
        path = ""
        for l in ai.split("\n"):
            if l.startswith("Path:"): path = l[5:].strip()
        if not path: await send_msg(chat, "Could not determine path"); return
        result = create_file(path, content, f"feat: add {fname}")
        await send_msg(chat, f"{result}\n📍 `{path}`")
        user_sessions.setdefault(uid,[]).append({"role":"assistant","content":ai})
    elif text and not text.startswith("/"):
        await send_msg(chat, "Thinking...")
        mem = read_memory()
        ctx = f"\nMemory:\n{mem[:1000]}" if mem else ""
        resp = await deepseek_chat([{"role":"user","content":f"{text}{ctx}"}], uid)
        if len(resp)>4000:
            for i in range(0,len(resp),4000): await send_msg(chat, resp[i:i+4000])
        else: await send_msg(chat, resp)
        user_sessions.setdefault(uid,[]).extend([{"role":"user","content":text},{"role":"assistant","content":resp}])

async def main():
    logger.info("🤖 SetRize Bot starting...")
    offset = 0
    async with httpx.AsyncClient() as c:
        while True:
            try:
                r = await c.get(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates",
                                params={"offset":offset,"timeout":30}, timeout=35)
                data = r.json()
                if not data.get("ok"):
                    continue
                for u in data["result"]:
                    offset = u["update_id"]+1
                    asyncio.create_task(process_update(u))
            except Exception as e:
                logger.error(f"Polling error: {e}")
                await asyncio.sleep(3)

if __name__=="__main__":
    asyncio.run(main())
  # Force redeploy v2
