import os
import json
from datetime import datetime

from googleapiclient.discovery import build
from google.oauth2.service_account import Credentials

from huggingface_hub import InferenceClient

from telegram import Update
from telegram.ext import Application, MessageHandler, CommandHandler, filters, ContextTypes


# ================== ENV ==================
def get_env(key):
    value = os.getenv(key)
    if not value:
        raise ValueError(f"Missing ENV: {key}")
    return value


SPREADSHEET_ID = get_env("SPREADSHEET_ID")
SHEET_NAME = get_env("SHEET_NAME")

TELEGRAM_BOT_TOKEN = get_env("TELEGRAM_BOT_TOKEN")
HUGGINGFACEHUB_API_TOKEN = get_env("HUGGINGFACEHUB_API_TOKEN")

GOOGLE_CREDENTIALS_JSON = get_env("GOOGLE_CREDENTIALS_JSON")

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


# ================== GOOGLE ==================
creds_info = json.loads(GOOGLE_CREDENTIALS_JSON)

creds = Credentials.from_service_account_info(
    creds_info,
    scopes=SCOPES
)


def get_service():
    return build("sheets", "v4", credentials=creds)


def save_to_sheet(row):
    try:
        service = get_service()

        service.spreadsheets().values().append(
            spreadsheetId=SPREADSHEET_ID,
            range=SHEET_NAME,
            valueInputOption="RAW",
            body={"values": [row]}
        ).execute()

        print("✅ Saved:", row)

    except Exception as e:
        print("❌ Sheet error:", e)


def get_last_order(user_id):
    service = get_service()

    result = service.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID,
        range=SHEET_NAME
    ).execute()

    rows = result.get("values", [])

    for row in reversed(rows):
        if len(row) > 8 and row[8] == str(user_id):
            return row

    return None


# ================== AI ==================
client = InferenceClient(
    model="mistralai/Mistral-7B-Instruct-v0.2",
    token=HUGGINGFACEHUB_API_TOKEN
)


def analyze_problem(text):
    prompt = f"""
أنت خبير سيارات.

حلل كلام المستخدم حتى لو كان عشوائي:

- استخرج نوع المشكلة
- مستوى الخطورة
- نصيحة سريعة

رد بالعربي فقط.

النص:
{text}
"""

    try:
        return client.text_generation(
            prompt,
            max_new_tokens=200,
            temperature=0.7
        )
    except:
        return "تم استلام طلبك 🚗"


# ================== MEMORY ==================
user_state = {}


# ================== START ==================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_state[user_id] = {"step": "name"}

    await update.message.reply_text("🚗 أهلاً! اكتب اسمك")


# ================== MAIN LOGIC ==================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    text = update.message.text.lower()

    # 🔥 حالة الطلب
    if "حالة" in text or "طلبي" in text:
        order = get_last_order(user_id)

        if order:
            await update.message.reply_text(f"""
📋 آخر طلب:

🚗 السيارة: {order[4]}
🔧 المشكلة: {order[5]}

📌 الحالة: {order[7]}
""")
        else:
            await update.message.reply_text("❌ ما عندك طلبات")
        return

    # 🔥 أول مرة
    if user_id not in user_state:
        user_state[user_id] = {"step": "name"}
        await update.message.reply_text("اكتب اسمك")
        return

    step = user_state[user_id]["step"]

    if step == "name":
        user_state[user_id]["name"] = text
        user_state[user_id]["step"] = "phone"
        await update.message.reply_text("📞 رقمك؟")
        return

    if step == "phone":
        user_state[user_id]["phone"] = text
        user_state[user_id]["step"] = "email"
        await update.message.reply_text("📧 ايميلك؟")
        return

    if step == "email":
        user_state[user_id]["email"] = text
        user_state[user_id]["step"] = "car"
        await update.message.reply_text("🚗 نوع السيارة؟")
        return

    if step == "car":
        user_state[user_id]["car"] = text
        user_state[user_id]["step"] = "problem"
        await update.message.reply_text("🔧 احكي المشكلة بأي طريقة")
        return

    if step == "problem":

        data = user_state[user_id]

        ai_result = analyze_problem(text)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        save_to_sheet([
            timestamp,
            data["name"],
            data["phone"],
            data["email"],
            data["car"],
            text,
            ai_result,
            "Pending",
            str(user_id)  # 🔥 مهم
        ])

        await update.message.reply_text(f"""
🚗 تم تسجيل طلبك

🧠 التحليل:
{ai_result}

📌 الحالة: Pending
""")

        user_state[user_id] = {"step": "name"}


# ================== MAIN ==================
def main():
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("🚗 Bot Running")
    app.run_polling()


if __name__ == "__main__":
    main()