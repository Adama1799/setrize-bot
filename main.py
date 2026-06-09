#!/usr/bin/env python3
"""
OpenClaw-inspired Telegram Bot for SetRise3 Repository Management
Production-grade AI Agent using DeepSeek
"""

import os
import logging
import re
from typing import Dict, Optional
from datetime import datetime

import httpx
from github import Github, GithubException
from github.Repository import Repository
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    CallbackQueryHandler,
)
from telegram.constants import ParseMode

# -------------------- Configuration --------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Environment variables (set these in Railway)
TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
DEEPSEEK_API_KEY = os.environ["DEEPSEEK_API_KEY"]
GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]
GITHUB_REPO = "rkm2004europe/setrise3"   # <-- المستودع المستهدف

# Allowed users: add your Telegram user ID here for exclusive access
ALLOWED_USERS = []  # e.g. [123456789]

# DeepSeek settings
DEEPSEEK_MODEL = "deepseek-chat"
MAX_TOKENS = 4000
TEMPERATURE = 0.3

# GitHub client
g = Github(GITHUB_TOKEN)
repo: Repository = g.get_repo(GITHUB_REPO)

# In-memory session storage per user
user_sessions: Dict[int, list] = {}

# Memory file in the target repository
MEMORY_FILE = "MEMORY.md"

# -------------------- System Prompt --------------------
SYSTEM_PROMPT = """أنت مساعد متطور لإدارة مشروع SetRize3 - تطبيق Flutter كامل.
أنت جزء من نظام OpenClaw-like Agent Runtime. قدراتك:
- تحليل الكود وتحديد موقعه الصحيح
- تعديل الملفات بناءً على وصف
- اقتراح تحسينات معمارية
- إنشاء Pull Requests احترافية
- الإجابة عن أسئلة حول المشروع
- حفظ واسترجاع تفضيلات المستخدم (ذاكرة)

هيكل المشروع SetRize3:
lib/
├── main.dart
├── core/          # Core functionality (theme, routes, di)
├── features/      # Feature modules
│   ├── auth/      # Authentication
│   ├── home/      # Home screen
│   ├── settings/  # Settings
│   └── ...
├── shared/        # Shared widgets, utils
└── l10n/          # Localization

عند إضافة ملف Dart جديد، اتبع Clean Architecture بدقة:
- data/datasources/
- data/repositories/
- domain/entities/
- domain/repositories/
- domain/usecases/
- presentation/providers/
- presentation/screens/
- presentation/widgets/

أجب بالعربية الفصحى المختصرة والمباشرة. كن دقيقاً ومهنياً."""

# -------------------- Helper Functions --------------------
async def deepseek_chat(messages: list, user_id: Optional[int] = None) -> str:
    """Send chat request to DeepSeek with session context."""
    try:
        # Build full context
        full_messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        if user_id and user_id in user_sessions:
            full_messages.extend(user_sessions[user_id][-10:])  # recent 10 msgs
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
        return f"❌ خطأ في الاتصال بـ DeepSeek: {str(e)}"

def get_file_from_github(file_path: str) -> Optional[str]:
    """Read file content from the repository."""
    try:
        content = repo.get_contents(file_path)
        return content.decoded_content.decode("utf-8")
    except:
        return None

def create_github_file(file_path: str, content: str, commit_msg: str) -> str:
    """Create new file on GitHub."""
    try:
        existing = repo.get_contents(file_path)
        return f"⚠️ الملف `{file_path}` موجود. استخدم /edit لتعديله."
    except:
        repo.create_file(file_path, commit_msg, content)
        return f"✅ تم إنشاء: `{file_path}`"

def update_github_file(file_path: str, content: str, commit_msg: str) -> str:
    """Update existing file."""
    try:
        existing = repo.get_contents(file_path)
        repo.update_file(file_path, commit_msg, content, existing.sha)
        return f"✅ تم تحديث: `{file_path}`"
    except GithubException as e:
        if e.status == 404:
            return create_github_file(file_path, content, commit_msg)
        return f"❌ خطأ: {str(e)}"

def create_pull_request(branch_name: str, file_path: str, content: str,
                        commit_msg: str, pr_title: str, pr_body: str) -> str:
    """Create a Pull Request."""
    try:
        base = repo.default_branch
        sb = repo.get_branch(base)
        repo.create_git_ref(f"refs/heads/{branch_name}", sb.commit.sha)

        try:
            existing = repo.get_contents(file_path, ref=branch_name)
            repo.update_file(file_path, commit_msg, content, existing.sha, branch=branch_name)
        except:
            repo.create_file(file_path, commit_msg, content, branch=branch_name)

        pr = repo.create_pull(title=pr_title, body=pr_body, head=branch_name, base=base)
        return f"🎉 PR #{pr.number}: [{pr.title}]({pr.html_url})"
    except Exception as e:
        return f"❌ فشل PR: {str(e)}"

def get_repo_structure(path: str = "lib", prefix: str = "") -> str:
    """Get directory tree string."""
    try:
        items = repo.get_contents(path)
        result = []
        for item in items:
            if item.type == "dir":
                result.append(f"{prefix}📁 {item.name}/")
                result.append(get_repo_structure(item.path, prefix + "  "))
            else:
                result.append(f"{prefix}📄 {item.name}")
        return "\n".join(result)
    except:
        return ""

def read_memory() -> str:
    content = get_file_from_github(MEMORY_FILE)
    return content if content else ""

def write_memory(content: str) -> bool:
    try:
        update_github_file(MEMORY_FILE, content, "📝 Update memory")
        return True
    except:
        return False

def add_to_memory(note: str) -> str:
    current = read_memory()
    timestamp = datetime.now().isoformat()
    new_entry = f"\n### {timestamp}\n{note}\n"
    updated = (current + new_entry) if current else f"# 🧠 SetRize3 Memory\n{new_entry}"
    if write_memory(updated):
        return "✅ تم الحفظ في الذاكرة."
    return "❌ فشل الحفظ."

# -------------------- Telegram Handlers --------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    keyboard = [
        [InlineKeyboardButton("📁 هيكل المشروع", callback_data="structure")],
        [InlineKeyboardButton("💬 مساعدة", callback_data="help")],
        [InlineKeyboardButton("🧠 الذاكرة", callback_data="memory")],
    ]
    markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        f"🤖 *مرحباً {user.first_name}!*\n\n"
        "أنا مساعد SetRize3 الذكي - إصدار OpenClaw.\n\n"
        "📄 أرسل ملف `.dart` لإضافته في مكانه الصحيح.\n"
        "💬 اطرح سؤالاً عن المشروع.\n"
        "الأوامر: /review, /edit, /pr, /memory, /structure",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=markup,
    )

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "structure":
        structure = get_repo_structure()
        text = f"📁 *الهيكل:*\n```\n{structure}\n```" if structure else "❌ تعذر قراءة الهيكل."
        await query.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
    elif query.data == "help":
        await query.message.reply_text(
            "📚 *الأوامر:*\n"
            "`/review <ملف|وصف>` - تحليل\n"
            "`/edit <مسار> <وصف>` - تعديل\n"
            "`/pr <عنوان> <وصف>` - إنشاء PR\n"
            "`/memory <نص>` - حفظ ملاحظة\n"
            "`/structure` - عرض الهيكل",
            parse_mode=ParseMode.MARKDOWN,
        )
    elif query.data == "memory":
        mem = read_memory()
        if mem:
            await query.message.reply_text(f"🧠 *الذاكرة:*\n{mem[:3000]}", parse_mode=ParseMode.MARKDOWN)
        else:
            await query.message.reply_text("🧠 الذاكرة فارغة.")

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if ALLOWED_USERS and user_id not in ALLOWED_USERS:
        return
    document = update.message.document
    if not document.file_name.endswith(".dart"):
        await update.message.reply_text("⚠️ أرسل ملف `.dart` فقط.")
        return
    msg = await update.message.reply_text("⏳ تحليل الملف...")
    try:
        file = await document.get_file()
        content = (await file.download_as_bytearray()).decode("utf-8")
        ai_resp = await deepseek_chat([{
            "role": "user",
            "content": f"اسم الملف: {document.file_name}\n\n```dart\n{content[:2000]}\n```\n"
                       f"حدد المسار الصحيح في المشروع. اكتب 'المسار:' ثم 'السبب:'."
        }], user_id)
        lines = ai_resp.split("\n")
        file_path = reason = ""
        for line in lines:
            if line.startswith("المسار:"):
                file_path = line.replace("المسار:", "").strip()
            elif line.startswith("السبب:"):
                reason = line.replace("السبب:", "").strip()
        if not file_path:
            await msg.edit_text("❌ لم أستطع تحديد المسار.")
            return
        commit = f"feat: add {document.file_name} via bot"
        result = create_github_file(file_path, content, commit)
        await msg.edit_text(f"{result}\n📍 `{file_path}`\n💡 {reason}", parse_mode=ParseMode.MARKDOWN)
        user_sessions.setdefault(user_id, []).append({"role": "assistant", "content": ai_resp})
    except Exception as e:
        await msg.edit_text(f"❌ خطأ: {e}")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if ALLOWED_USERS and user_id not in ALLOWED_USERS:
        return
    text = update.message.text
    msg = await update.message.reply_text("⏳ معالجة...")
    try:
        memory_context = ""
        mem = read_memory()
        if mem:
            memory_context = f"\n\nذاكرة المشروع:\n{mem[:1000]}"
        resp = await deepseek_chat([{"role": "user", "content": f"{text}{memory_context}"}], user_id)
        if len(resp) > 4000:
            parts = [resp[i:i+4000] for i in range(0, len(resp), 4000)]
            await msg.edit_text(parts[0], parse_mode=ParseMode.MARKDOWN)
            for part in parts[1:]:
                await update.message.reply_text(part, parse_mode=ParseMode.MARKDOWN)
        else:
            await msg.edit_text(resp, parse_mode=ParseMode.MARKDOWN)
        user_sessions.setdefault(user_id, []).extend([
            {"role": "user", "content": text},
            {"role": "assistant", "content": resp}
        ])
    except Exception as e:
        await msg.edit_text(f"❌ خطأ: {e}")

async def review_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("استخدم: `/review <مسار_ملف_أو_وصف>`", parse_mode=ParseMode.MARKDOWN)
        return
    target = " ".join(context.args)
    msg = await update.message.reply_text("🔍 تحليل...")
    code = get_file_from_github(target) if "/" in target else None
    prompt = f"حلل هذا الملف:\n```dart\n{code[:3000]}\n```" if code else f"راجع هذا: {target}"
    resp = await deepseek_chat([{"role": "user", "content": prompt}], update.effective_user.id)
    await msg.edit_text(resp, parse_mode=ParseMode.MARKDOWN)

async def edit_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text("استخدم: `/edit <مسار> <وصف التعديل>`", parse_mode=ParseMode.MARKDOWN)
        return
    path = context.args[0]
    desc = " ".join(context.args[1:])
    current = get_file_from_github(path)
    if not current:
        await update.message.reply_text("❌ الملف غير موجود.")
        return
    msg = await update.message.reply_text("✏️ تعديل...")
    prompt = f"عدل الملف `{path}`:\n```dart\n{current[:3000]}\n```\nالتعديل المطلوب: {desc}\nأعد الكود الكامل بعد التعديل."
    resp = await deepseek_chat([{"role": "user", "content": prompt}], update.effective_user.id)
    # Naive extraction of code block
    code_match = re.search(r"```dart\n(.*?)```", resp, re.DOTALL)
    new_code = code_match.group(1) if code_match else resp
    result = update_github_file(path, new_code, f"✏️ edit {path}: {desc}")
    await msg.edit_text(f"{result}\n\n{resp[:2000]}", parse_mode=ParseMode.MARKDOWN)

async def pr_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("ميزة Pull Request قيد التطوير النهائي. حالياً يمكنك استخدام /edit ثم رفع PR يدوياً.")

async def memory_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        mem = read_memory()
        await update.message.reply_text(f"🧠 الذاكرة:\n{mem[:3000]}" if mem else "فارغة.")
        return
    note = " ".join(context.args)
    result = add_to_memory(note)
    await update.message.reply_text(result)

async def structure_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    structure = get_repo_structure()
    await update.message.reply_text(f"📁 الهيكل:\n```\n{structure}\n```" if structure else "❌ خطأ.")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Update {update} caused error {context.error}")

# -------------------- Main --------------------
def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("review", review_cmd))
    app.add_handler(CommandHandler("edit", edit_cmd))
    app.add_handler(CommandHandler("pr", pr_cmd))
    app.add_handler(CommandHandler("memory", memory_cmd))
    app.add_handler(CommandHandler("structure", structure_cmd))
    app.add_handler(MessageHandler(filters.Document.FileExtension("dart"), handle_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_error_handler(error_handler)

    logger.info("🤖 SetRize Bot (OpenClaw) starting...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
