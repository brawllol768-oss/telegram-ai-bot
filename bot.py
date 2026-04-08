import os
import requests
import threading
from flask import Flask
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ========== ВАШИ ТОКЕНЫ ==========
TELEGRAM_TOKEN = "8738211573:AAE1r3BEW6zdRR9JK8R2LwQf_NlgyBfiiUQ"
OPENROUTER_KEY = "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"
# =================================

# Создаём веб-сервер для пингов
web_app = Flask(__name__)

@web_app.route('/')
@web_app.route('/health')
def health():
    return "OK", 200

def run_web():
    web_app.run(host='0.0.0.0', port=10000)

# Запускаем веб-сервер в отдельном потоке
threading.Thread(target=run_web, daemon=True).start()

# Клавиатура с кнопками
def get_main_keyboard():
    keyboard = [
        [KeyboardButton("📝 Задать вопрос ИИ")],
        [KeyboardButton("ℹ️ О боте"), KeyboardButton("🆘 Помощь")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 Привет! Я бот с искусственным интеллектом.\n\nНажми на кнопку ниже, чтобы задать вопрос.",
        reply_markup=get_main_keyboard()
    )

# Команда /help
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📌 Как пользоваться:\n• Нажми «📝 Задать вопрос ИИ» и напиши вопрос\n• Или просто отправь любое сообщение"
    )

# Кнопка "О боте"
async def about(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("ℹ️ Бот работает через OpenRouter на модели GPT-3.5")

# Главная логика — запрос к ИИ
async def ask_ai(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    
    if user_text == "📝 Задать вопрос ИИ":
        await update.message.reply_text("✍️ Напишите ваш вопрос:")
        return
    
    await update.message.chat.send_action(action="typing")
    
    headers = {
        "Authorization": f"Bearer {OPENROUTER_KEY}",
        "Content-Type": "application/json"
    }
    
    data = {
        "model": "openai/gpt-3.5-turbo",
        "messages": [{"role": "user", "content": user_text}]
    }
    
    try:
        response = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=data, timeout=30)
        result = response.json()
        answer = result["choices"][0]["message"]["content"]
        await update.message.reply_text(answer, reply_markup=get_main_keyboard())
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}\nПопробуйте позже.", reply_markup=get_main_keyboard())

# Запуск бота
def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.Regex("^ℹ️ О боте$"), about))
    app.add_handler(MessageHandler(filters.Regex("^🆘 Помощь$"), help_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, ask_ai))
    app.run_polling()

if __name__ == "__main__":
    main()
