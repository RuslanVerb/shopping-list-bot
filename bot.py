import json
import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
DATA_FILE = Path(__file__).parent / "lists.json"

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# ---------- Зберігання даних ----------

def load_data() -> dict:
    if DATA_FILE.exists():
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_data(data: dict) -> None:
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_chat_list(data: dict, chat_id: str) -> list:
    return data.setdefault(chat_id, [])


# ---------- Клавіатура ----------

def build_keyboard(items: list) -> InlineKeyboardMarkup:
    buttons = []
    for idx, item in enumerate(items):
        mark = "✅" if item["done"] else "⬜"
        text = f"{mark} {item['name']}"
        buttons.append(
            [
                InlineKeyboardButton(text, callback_data=f"toggle:{idx}"),
                InlineKeyboardButton("❌", callback_data=f"delete:{idx}"),
            ]
        )
    if items:
        buttons.append([InlineKeyboardButton("🗑 Очистити все", callback_data="clear")])
    return InlineKeyboardMarkup(buttons)


def render_text(items: list) -> str:
    if not items:
        return "🛒 Список покупок порожній.\nДодай пункт командою /add <товар>"
    done = sum(1 for i in items if i["done"])
    return f"🛒 Список покупок ({done}/{len(items)} куплено):"


# ---------- Команди ----------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Привіт! Я бот-список покупок 🛒\n\n"
        "Команди:\n"
        "/add <товар> — додати пункт\n"
        "/list — показати список з чекбоксами\n"
        "/clear — очистити список\n\n"
        "Натискай на пункт у списку, щоб позначити його купленим ✅"
    )


async def add_item(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = str(update.effective_chat.id)
    text = " ".join(context.args).strip()

    if not text:
        await update.message.reply_text("Напиши так: /add молоко")
        return

    data = load_data()
    items = get_chat_list(data, chat_id)
    items.append({"name": text, "done": False})
    save_data(data)

    await update.message.reply_text(
        render_text(items), reply_markup=build_keyboard(items)
    )


async def list_items(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = str(update.effective_chat.id)
    data = load_data()
    items = get_chat_list(data, chat_id)

    await update.message.reply_text(
        render_text(items), reply_markup=build_keyboard(items)
    )


async def clear_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = str(update.effective_chat.id)
    data = load_data()
    data[chat_id] = []
    save_data(data)

    await update.message.reply_text("Список очищено 🧹")


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    chat_id = str(update.effective_chat.id)
    data = load_data()
    items = get_chat_list(data, chat_id)

    action, _, arg = query.data.partition(":")

    if action == "toggle":
        idx = int(arg)
        if 0 <= idx < len(items):
            items[idx]["done"] = not items[idx]["done"]
    elif action == "delete":
        idx = int(arg)
        if 0 <= idx < len(items):
            items.pop(idx)
    elif action == "clear":
        items.clear()

    save_data(data)

    await query.answer()
    await query.edit_message_text(
        render_text(items), reply_markup=build_keyboard(items)
    )


async def unknown_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Будь-яке повідомлення без команди — трактуємо як новий пункт списку
    chat_id = str(update.effective_chat.id)
    text = update.message.text.strip()
    if not text:
        return

    data = load_data()
    items = get_chat_list(data, chat_id)
    items.append({"name": text, "done": False})
    save_data(data)

    await update.message.reply_text(
        render_text(items), reply_markup=build_keyboard(items)
    )


def main() -> None:
    if not BOT_TOKEN:
        raise RuntimeError(
            "Не знайдено BOT_TOKEN. Створи файл .env на основі .env.example "
            "і встав туди токен від @BotFather."
        )

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("add", add_item))
    app.add_handler(CommandHandler("list", list_items))
    app.add_handler(CommandHandler("clear", clear_list))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, unknown_text))

    logger.info("Бот запущено...")
    app.run_polling()


if __name__ == "__main__":
    main()
