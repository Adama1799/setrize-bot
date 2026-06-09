import os
import asyncio
import logging
import httpx
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
- lib/features/X/data/datasources/
- lib/features/X/data/repositories/
- lib/features/X/domain/entities/
- lib/features/X/domain/repositories/
- lib/features/X/domain/usecases/
- lib/features/X/presentation/providers/
- lib/features/X/presentation/screens/
- lib/features/X/presentation/widgets/"""

async def send_message(chat_id, text):
    async with httpx.AsyncClient() as client:
        await client.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
        )

async def get_file(file_id):
    async with httpx.AsyncClient() as client:
        r = await client.get(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getFile?file_id={file_id}")
        path = r.json()["result"]["file_path"]
        r2 = await client.get(f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{path}")
        return r2.content

def ask_deepseek(messages):
    import requests
    response = requests.post(
        "https://api.deepseek.com/chat/completions",
        headers={"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"},
        json={"model": "deepseek-chat", "messages": [{"role": "system", "content": SYSTEM_PROMPT}] + messages, "max_tokens": 2000}
    )
    return response.json()["choices"][0]["message"]["content"]

def put_file_github(file_path, content, msg):
    try:
        existing = repo.get_contents(file_path)
        repo.update_file(file_path, msg, content, existing.sha)
        return f"✅ تم تحديث: `{file_path}`"
    except:
        repo.create_file(file_path, msg, content)
        return f"✅ تم إنشاء: `{file_path}`"

async def process_update(update):
    message = update.get("message", {})
    chat_id = message.get("chat", {}).get("id")
    text = message.get("text", "")
    document = message.get("document")

    if not chat_id:
        return

    if text == "/start":
        await send_message(chat_id,
            "🤖 مرحباً! أنا مساعد SetRize\n\n"
            "أرسل لي:\n"
            "📄 ملف Dart ← أضعه في مكانه الصح\n"
            "💬 سؤال ← أجاوبك عن المشروع\n"
            "📁 /structure ← هيكل المشروع"
        )
    elif text == "/structure":
        await send_message(chat_id, "⏳ جاري قراءة المشروع...")
        try:
            contents = repo.get_contents("lib")
            txt = "📁 هيكل SetRize:\n\n"
            for item in contents:
                txt += f"{'📁' if item.type == 'dir' else '📄'} {item.path}\n"
            await send_message(chat_id, txt)
        except Exception as e:
            await send_message(chat_id, f"❌ خطأ: {e}")
    elif document:
        name = document.get("file_name", "")
        if not name.endswith(".dart"):
            await send_message(chat_id, "⚠️ أرسل ملف Dart فقط (.dart)")
            return
        await send_message(chat_id, "⏳ جاري تحليل الملف...")
        content_bytes = await get_file(document["file_id"])
        content = content_bytes.decode("utf-8")
        messages = [{"role": "user", "content": f"اسم الملف: {name}\n\nمحتوى الملف:\n```dart\n{content}\n```\n\nحدد المسار الصح في السطر الأول فقط."}]
        ai_response = ask_deepseek(messages)
        file_path = ai_response.strip().split("\n")[0].strip()
        result = put_file_github(file_path, content, f"feat: add {name} via SetRize Bot")
        await send_message(chat_id, f"{result}\n\n📍 `{file_path}`\n\n💡 {ai_response}")
    elif text:
        await send_message(chat_id, "⏳ جاري التفكير...")
        response = ask_deepseek([{"role": "user", "content": text}])
        await send_message(chat_id, response)

async def main():
    offset = 0
    logging.info("✅ SetRize Bot شغال!")
    async with httpx.AsyncClient() as client:
        while True:
            try:
                r = await client.get(
                    f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates",
                    params={"offset": offset, "timeout": 30},
                    timeout=35
                )
                updates = r.json().get("result", [])
                for update in updates:
                    offset = update["update_id"] + 1
                    await process_update(update)
            except Exception as e:
                logging.error(f"خطأ: {e}")
                await asyncio.sleep(3)

if __name__ == "__main__":
    asyncio.run(main())
