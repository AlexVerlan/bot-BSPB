import os
import sqlite3
import random
import logging
from datetime import datetime, timedelta

from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler, MessageHandler, filters

# --- НАСТРОЙКИ ---
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
MESSAGES_FILE = "messages.txt"
DB_FILE = "users.db"

# ID администратора (замените на свой)
ADMIN_IDS = [1030669850]

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- БАЗА ДАННЫХ ---
def init_db():
    """Создаёт таблицу пользователей, если её нет."""
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            joined_date TEXT,
            has_accepted INTEGER DEFAULT 0,
            accepted_date TEXT
        )
    """)
    conn.commit()
    conn.close()
    logger.info("База данных инициализирована.")

def add_user(user_id, username, first_name):
    """Добавляет пользователя при первом /start (или обновляет имя)."""
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("""
        INSERT OR IGNORE INTO users (user_id, username, first_name, joined_date)
        VALUES (?, ?, ?, ?)
    """, (user_id, username, first_name, datetime.now().strftime("%Y-%m-%d %H:%M")))
    # Если пользователь уже был, обновим имя (на случай смены)
    cur.execute("UPDATE users SET first_name = ?, username = ? WHERE user_id = ?",
                (first_name, username, user_id))
    conn.commit()
    conn.close()

def set_accepted(user_id):
    """Помечает, что пользователь согласился участвовать."""
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("""
        UPDATE users SET has_accepted = 1, accepted_date = ?
        WHERE user_id = ? AND has_accepted = 0
    """, (datetime.now().strftime("%Y-%m-%d %H:%M"), user_id))
    conn.commit()
    conn.close()
    logger.info(f"Пользователь {user_id} согласился на участие.")

def is_accepted(user_id):
    """Проверяет, дал ли пользователь согласие."""
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT has_accepted FROM users WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()
    return row is not None and row[0] == 1

def get_statistics():
    """Собирает статистику для админа."""
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM users")
    total = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM users WHERE has_accepted = 1")
    accepted = cur.fetchone()[0]
    today = datetime.now().strftime("%Y-%m-%d")
    cur.execute("SELECT COUNT(*) FROM users WHERE joined_date LIKE ?", (f"{today}%",))
    new_today = cur.fetchone()[0]
    conn.close()
    return {"total": total, "accepted": accepted, "new_today": new_today}

# --- РАБОТА С ЗАДАНИЯМИ ---
def load_messages():
    """Загружает список заданий из файла (разделены пустыми строками)."""
    try:
        with open(MESSAGES_FILE, 'r', encoding='utf-8') as f:
            content = f.read()
        raw = content.split('\n\n')
        messages = [msg.strip() for msg in raw if msg.strip()]
        logger.info(f"Загружено {len(messages)} заданий")
        return messages
    except FileNotFoundError:
        logger.error(f"Файл {MESSAGES_FILE} не найден!")
        return []

def get_random_task():
    """Возвращает случайное задание из списка."""
    tasks = load_messages()
    if not tasks:
        return None
    return random.choice(tasks)

# --- ОБРАБОТЧИКИ КОМАНД ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Приветствие и предложение участвовать."""
    user = update.effective_user
    user_id = user.id
    username = user.username or "нет username"
    first_name = user.first_name or ""

    add_user(user_id, username, first_name)

    welcome = (
        f"Привет, {first_name}!\n\n"
        "Этот бот создан, чтобы поближе познакомить тебя с корпоративной ценностью "
        "«Развиваю Банк и развиваюсь сам».\n"
        "Следуя ей, мы развиваем свои навыки, используем в работе лучшие практики, "
        "постоянно совершенствуемся и помогаем развиваться коллегам, делясь экспертизой.\n\n"
        "Хочешь принять участие в челлендже «Слепой спринт»?"
    )
    keyboard = [
        [InlineKeyboardButton("✅ Да", callback_data="yes"),
         InlineKeyboardButton("❌ Нет", callback_data="no")]
    ]
    await update.message.reply_text(welcome, reply_markup=InlineKeyboardMarkup(keyboard))

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Статистика (только для админов)."""
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("⛔ Нет доступа.")
        return

    stats = get_statistics()
    moscow_time = datetime.now() + timedelta(hours=3)
    report = (
        "📊 **Статистика бота «Развиваюсь с БСПБ»**\n\n"
        f"👥 Всего пользователей: {stats['total']}\n"
        f"✅ Согласились участвовать: {stats['accepted']}\n"
        f"🆕 Новых сегодня: {stats['new_today']}\n\n"
        f"📅 Отчёт от: {moscow_time.strftime('%d.%m.%Y %H:%M')}"
    )
    await update.message.reply_text(report, parse_mode='Markdown')

# --- ОБРАБОТЧИК КНОПОК ---
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Реакция на кнопки Да / Нет."""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data

    if data == "yes":
        set_accepted(user_id)
        instruction = (
            "Я отправлю тебе задание, которое поможет познакомиться с ценностью на практике. "
            "Выполни его с 6 по 24 июля и поделись полученным опытом на форуме корпоративного портала.\n"
            "Все ссылки и информацию о проектах, которые затрагивают задачи, можно найти на портале.\n"
            "Участвовать можно неоднократно.\n\n"
            "Начнем?"
        )
        await query.message.reply_text(instruction)

        # Сразу выдаём первое задание
        task = get_random_task()
        if task:
            await query.message.reply_text(task)
        else:
            await query.message.reply_text("⚠️ Задания временно недоступны. Попробуйте позже.")
    elif data == "no":
        await query.message.reply_text("Жаль. Если передумаешь, просто напиши мне или нажми /start.")

# --- ОБРАБОТЧИК ТЕКСТОВЫХ СООБЩЕНИЙ ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Любое текстовое сообщение → выдать случайное задание (если пользователь согласился)."""
    user_id = update.effective_user.id

    # Проверяем, давал ли пользователь согласие (было нажато «Да»)
    if not is_accepted(user_id):
        await update.message.reply_text(
            "Чтобы получить задание, сначала нажмите /start и согласитесь на участие в челлендже."
        )
        return

    task = get_random_task()
    if task:
        await update.message.reply_text(task)
    else:
        await update.message.reply_text("⚠️ Задания временно недоступны. Попробуйте позже.")

# --- ГЛАВНАЯ ФУНКЦИЯ ---
def main():
    init_db()

    if not os.path.exists(MESSAGES_FILE):
        print(f"⚠️ ВНИМАНИЕ: Файл {MESSAGES_FILE} не найден!")
        print("Создайте его и добавьте задания (каждое отделяйте пустой строкой)")

    print("🤖 Бот «Развиваюсь с БСПБ» запущен...")
    print("📩 Отправьте любое сообщение, чтобы получить случайное задание.")

    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    application.run_polling()

if __name__ == "__main__":
    main()