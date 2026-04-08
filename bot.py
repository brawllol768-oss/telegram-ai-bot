import os
import requests
import threading
from flask import Flask
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext

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
def start(update: Update, context: CallbackContext):
    update.message.reply_text(
        "🤖 Привет! Я бот с искусственным интеллектом.\n\nНажми на кнопку ниже, чтобы задать вопрос.",
        reply_markup=get_main_keyboard()
    )

# Команда /help
def help_command(update: Update, context: CallbackContext):
    update.message.reply_text(
        "📌 Как пользоваться:\n• Нажми «📝 Задать вопрос ИИ» и напиши вопрос\n• Или просто отправь любое сообщение"
    )

# Кнопка "О боте"
def about(update: Update, context: CallbackContext):
    update.message.reply_text("ℹ️ Бот работает через OpenRouter на модели GPT-3.5")

# Главная логика — запрос к ИИ
def ask_ai(update: Update, context: CallbackContext):
    user_text = update.message.text
    
    if user_text == "📝 Задать вопрос ИИ":
        update.message.reply_text("✍️ Напишите ваш вопрос:")
        return
    
    update.message.chat.send_action(action="typing")
    
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
        update.message.reply_text(answer, reply_markup=get_main_keyboard())
    except Exception as e:
        update.message.reply_text(f"❌ Ошибка: {e}\nПопробуйте позже.", reply_markup=get_main_keyboard())

# Запуск бота
def main():
    updater = Updater(TELEGRAM_TOKEN, use_context=True)
    dp = updater.dispatcher
    
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("help", help_command))
    dp.add_handler(MessageHandler(Filters.regex("^ℹ️ О боте$"), about))
    dp.add_handler(MessageHandler(Filters.regex("^🆘 Помощь$"), help_command))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, ask_ai))
    
    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
