import os
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, filters, ContextTypes
import requests
from github import Github

logging.basicConfig(level=logging.INFO)

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
DEEPSEEK_API_KEY = os.environ["DEEPSEEK_API_KEY"]
GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]
GITHUB_REPO = "rkm2004europe/setrise3"

g = Github(GITHUB_TOKEN)
repo = g.get_repo(GITHUB_REPO)

SYSTEM_PROMPT = """أنت مساعد متخصص في مشروع SetRize — تطبيق Flutter بـ Clean Architecture.
هيكل المشروع:
- lib/ ← كود Dart الرئيسي
- core/ ← Clean Architecture core
- features/ ← كل feature منفصلة

مهمتك:
1. تدرس الملفات المرسلة
2. تحدد المسار الصح في المشروع
3. تضع الملف في مكانه الصح على GitHub
4. تشرح ماذا فعلت

عند تحديد المسار اتبع Clean Architecture:
- data/datasources/ ← API calls
- data/repositories/ ← repository implementations  
- domain/entities/ ← models
- domain/repositories/ ← interfaces
- domain/usecases/ ← business logic
- presentation/providers/ ← Riverpod providers
- presentation/screens/ ← UI screens
- presentation/widgets/ ← reusable widgets"""

def ask_deepseek(messages):
    response = requests.post(
        "https://api.deepseek.com/chat/completions",
        headers={
            "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
            "Content-Type": "application/json"
        },
        json={
            "model": "deepseek-chat",
            "messages": [{"role": "system", "content": SYSTEM_PROMPT}] + messages,
            "max_tokens": 2000
        }
    )
    return response.json()["choices"][0]["message"]["content"]

def put_file_on_github(file_path, content, commit_message):
    try:
        existing = repo.get_contents(file_path)
        repo.update_file(file_path, commit_message, content, existing.sha)
        return f"✅ تم تحديث: `{file_path}`"
    except:
        repo.create_file(file_path, commit_message, content)
        return f"✅ تم إنشاء: `{file_path}`"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 مرحباً! أنا مساعد SetRize\n\n"
        "أرسل لي:\n"
        "📄 ملف Dart ← أضعه في مكانه الصح\n"
        "💬 سؤال ← أجاوبك عن المشروع\n"
        "📁 /structure ← أعرض هيكل المشروع"
    )

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document
    if not doc.file_name.endswith(".dart"):
        await update.message.reply_text("⚠️ أرسل ملف Dart فقط (.dart)")
        return

    await update.message.reply_text("⏳ جاري تحليل الملف...")

    file = await doc.get_file()
    content_bytes = await file.download_as_bytearray()
    content = content_bytes.decode("utf-8")

    messages = [{
        "role": "user",
        "content": f"اسم الملف: {doc.file_name}\n\nمحتوى الملف:\n```dart\n{content}\n```\n\nحدد المسار الصح في SetRize وأعطني:\n1. المسار الكامل (مثال: lib/features/auth/data/datasources/auth_remote_datasource.dart)\n2. شرح سبب اختيار هذا المسار\n\nاكتب المسار في السطر الأول فقط بدون أي شيء آخر."
    }]

    ai_response = ask_deepseek(messages)
    lines = ai_response.strip().split("\n")
    file_path = lines[0].strip()

    result = put_file_on_github(file_path, content, f"feat: add {doc.file_name} via SetRize Bot")

    await update.message.reply_text(
        f"{result}\n\n"
        f"📍 المسار: `{file_path}`\n\n"
        f"💡 {ai_response}"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    await update.message.reply_text("⏳ جاري التفكير...")

    messages = [{"role": "user", "content": text}]
    response = ask_deepseek(messages)
    await update.message.reply_text(response)

async def structure(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ جاري قراءة المشروع...")
    try:
        contents = repo.get_contents("lib")
        structure_text = "📁 هيكل SetRize:\n\n"
        for item in contents:
            structure_text += f"{'📁' if item.type == 'dir' else '📄'} {item.path}\n"
        await update.message.reply_text(structure_text)
    except Exception as e:
        await update.message.reply_text(f"❌ خطأ: {e}")

app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("structure", structure))
app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

import asyncio
asyncio.run(app.run_polling())
