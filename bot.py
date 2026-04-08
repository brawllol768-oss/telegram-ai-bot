import os
import requests
import threading
import telebot
from flask import Flask

# ========== ВАШИ ТОКЕНЫ ==========
TELEGRAM_TOKEN = "8738211573:AAE1r3BEW6zdRR9JK8R2LwQf_NlgyBfiiUQ"
OPENROUTER_KEY = "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"
# =================================

# Создаём бота
bot = telebot.TeleBot(TELEGRAM_TOKEN)

# Создаём веб-сервер для пингов (чтобы бот не засыпал)
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
    keyboard = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.row("📝 Задать вопрос ИИ")
    keyboard.row("ℹ️ О боте", "🆘 Помощь")
    return keyboard

# Обработчик команды /start
@bot.message_handler(commands=['start'])
def start(message):
    bot.send_message(
        message.chat.id,
        "🤖 Привет! Я бот с искусственным интеллектом.\n\nНажми на кнопку ниже, чтобы задать вопрос.",
        reply_markup=get_main_keyboard()
    )

# Обработчик команды /help
@bot.message_handler(commands=['help'])
def help_command(message):
    bot.send_message(
        message.chat.id,
        "📌 Как пользоваться:\n• Нажми «📝 Задать вопрос ИИ» и напиши вопрос\n• Или просто отправь любое сообщение"
    )

# Обработчик кнопки "О боте"
@bot.message_handler(func=lambda message: message.text == "ℹ️ О боте")
def about(message):
    bot.send_message(message.chat.id, "ℹ️ Бот работает через OpenRouter на модели GPT-3.5")

# Обработчик кнопки "Помощь"
@bot.message_handler(func=lambda message: message.text == "🆘 Помощь")
def help_button(message):
    help_command(message)

# Обработчик кнопки "Задать вопрос"
@bot.message_handler(func=lambda message: message.text == "📝 Задать вопрос ИИ")
def ask_question(message):
    msg = bot.send_message(message.chat.id, "✍️ Напишите ваш вопрос:")
    bot.register_next_step_handler(msg, ask_ai)

# Основная логика запроса к ИИ (исправленная)
def ask_ai(message):
    user_text = message.text
    
    bot.send_chat_action(message.chat.id, 'typing')
    
    headers = {
        "Authorization": f"Bearer {OPENROUTER_KEY}",
        "Content-Type": "application/json"
    }
    
    # Используем стабильную бесплатную модель
    data = {
        "model": "mistralai/mistral-7b-instruct:free",
        "messages": [{"role": "user", "content": user_text}]
    }
    
    try:
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json=data,
            timeout=45
        )
        result = response.json()
        
        # Проверяем на наличие ошибки в ответе
        if 'error' in result:
            error_msg = result['error'].get('message', 'Неизвестная ошибка API')
            bot.send_message(
                message.chat.id,
                f"❌ Ошибка API: {error_msg}\nПопробуйте позже.",
                reply_markup=get_main_keyboard()
            )
            return
        
        # Проверяем наличие поля choices
        if 'choices' not in result or len(result['choices']) == 0:
            bot.send_message(
                message.chat.id,
                "❌ Модель вернула пустой ответ. Попробуйте задать вопрос иначе.",
                reply_markup=get_main_keyboard()
            )
            return
        
        answer = result["choices"][0]["message"]["content"]
        bot.send_message(message.chat.id, answer, reply_markup=get_main_keyboard())
        
    except requests.exceptions.Timeout:
        bot.send_message(
            message.chat.id,
            "❌ Превышено время ожидания. Попробуйте позже.",
            reply_markup=get_main_keyboard()
        )
    except Exception as e:
        error_text = str(e)
        # Если ошибка связана с 'choices', даём понятное пояснение
        if "choices" in error_text:
            bot.send_message(
                message.chat.id,
                "❌ Модель временно недоступна. Попробуйте через минуту.\n\nЕсли ошибка повторяется, напишите /start",
                reply_markup=get_main_keyboard()
            )
        else:
            bot.send_message(
                message.chat.id,
                f"❌ Ошибка: {error_text}\nПопробуйте позже.",
                reply_markup=get_main_keyboard()
            )

# Обработчик всех остальных текстовых сообщений
@bot.message_handler(func=lambda message: True)
def echo_all(message):
    ask_ai(message)

# Запуск бота
if __name__ == "__main__":
    print("🤖 Бот запущен...")
    bot.infinity_polling(skip_pending=True)
