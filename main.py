import os
import json
from datetime import datetime

from googleapiclient.discovery import build
from google.oauth2.service_account import Credentials

from huggingface_hub import InferenceClient

from telegram import Update
from telegram.ext import Application, MessageHandler, CommandHandler, filters, ContextTypes


# ================== ENV SAFETY ==================
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


# ================== GOOGLE SHEETS AUTH ==================
creds_info = json.loads(GOOGLE_CREDENTIALS_JSON)

creds = Credentials.from_service_account_info(
    creds_info,
    scopes=SCOPES
)


def get_service():
    return build("sheets", "v4", credentials=creds)


def save_to_sheet(row):
    service = get_service()

    service.spreadsheets().values().append(
        spreadsheetId=SPREADSHEET_ID,
        range=SHEET_NAME,
        valueInputOption="RAW",
        body={"values": [row]}
    ).execute()


# ================== AI (HUGGING FACE) ==================
client = InferenceClient(
    model="mistralai/Mistral-7B-Instruct-v0.2",
    token=HUGGINGFACEHUB_API_TOKEN
)


def analyze_problem(text):
    prompt = f"""
أنت مساعد كراج سيارات ذكي.

حلل المشكلة بالعربية فقط:

1. نوع المشكلة
2. الخطورة (منخفض / متوسط / عالي)
3. الحل المقترح

المشكلة:
{text}
"""

    try:
        return client.text_generation(
            prompt,
            max_new_tokens=250,
            temperature=0.7
        )
    except Exception as e:
        print("AI error:", e)
        return "تم استلام الطلب وسيتم مراجعته قريباً 🚗"


# ================== MEMORY ==================
user_state = {}


# ================== START ==================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_state[user_id] = {"step": "name"}

    await update.message.reply_text(
        "🚗 أهلاً بك في Garage AI Bot\nاكتب اسمك الكامل"
    )


# ================== FLOW ==================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    text = update.message.text

    if user_id not in user_state:
        user_state[user_id] = {"step": "name"}
        await update.message.reply_text("🚗 اكتب اسمك الكامل")
        return

    step = user_state[user_id]["step"]

    # NAME
    if step == "name":
        user_state[user_id]["name"] = text
        user_state[user_id]["step"] = "phone"
        await update.message.reply_text("📞 اكتب رقم الهاتف")
        return

    # PHONE
    if step == "phone":
        user_state[user_id]["phone"] = text
        user_state[user_id]["step"] = "email"
        await update.message.reply_text("📧 اكتب الإيميل")
        return

    # EMAIL
    if step == "email":
        user_state[user_id]["email"] = text
        user_state[user_id]["step"] = "car"
        await update.message.reply_text("🚗 اكتب نوع السيارة")
        return

    # CAR
    if step == "car":
        user_state[user_id]["car"] = text
        user_state[user_id]["step"] = "problem"
        await update.message.reply_text("🔧 اكتب المشكلة")
        return

    # PROBLEM
    if step == "problem":

        name = user_state[user_id]["name"]
        phone = user_state[user_id]["phone"]
        email = user_state[user_id]["email"]
        car = user_state[user_id]["car"]

        ai_result = analyze_problem(text)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        save_to_sheet([
            timestamp,
            name,
            phone,
            email,
            car,
            text,
            ai_result,
            "Pending"
        ])

        await update.message.reply_text(f"""
🚗 تم استلام طلبك يا {name}

📞 {phone}
📧 {email}
🚗 {car}

🧠 تحليل المشكلة:
{ai_result}

📌 الحالة: Pending
""")

        user_state[user_id] = {"step": "name"}


# ================== MAIN ==================
def main():
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("🚗 Bot Running (Production Ready)")
    app.run_polling()


if __name__ == "__main__":
    main()