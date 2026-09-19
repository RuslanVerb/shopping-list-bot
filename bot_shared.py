import json
import logging
import os
import secrets
import string
from pathlib import Path

from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import TelegramError
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
DATA_FILE = Path("/data/shared_data.json")

MAX_MEMBERS = 2
CODE_CHARS = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger(__name__)


# ---------- Зберігання даних ----------

def load_data() -> dict:
    if DATA_FILE.exists():
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        data.setdefault("lists", {})
        data.setdefault("users", {})
        return data

    return {
        "lists": {},
        "users": {},
    }


def save_data(data: dict) -> None:
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ---------- Робота зі списками ----------

def get_user_list_id(data: dict, chat_id: str):
    return data["users"].get(chat_id)


def generate_invite_code(data: dict) -> str:
    while True:
        code = "".join(
            secrets.choice(CODE_CHARS)
            for _ in range(6)
        )

        exists = any(
            item["invite_code"] == code
            for item in data["lists"].values()
        )

        if not exists:
            return code


def create_list(data: dict, chat_id: str) -> str:
    list_id = secrets.token_hex(8)

    data["lists"][list_id] = {
        "invite_code": generate_invite_code(data),
        "members": [chat_id],
        "items": [],
        "messages": {},
    }

    data["users"][chat_id] = list_id

    return list_id


def find_list_by_code(data: dict, code: str):
    code = code.upper().strip()

    for list_id, shopping_list in data["lists"].items():
        if shopping_list["invite_code"] == code:
            return list_id

    return None


# ---------- Клавіатури ----------

def main_menu_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [
            InlineKeyboardButton(
                "➕ Створити список",
                callback_data="create_list",
            )
        ],
        [
            InlineKeyboardButton(
                "🔗 Приєднатися до списку",
                callback_data="join_mode",
            )
        ],
    ]

    return InlineKeyboardMarkup(keyboard)


def build_keyboard(shopping_list: dict) -> InlineKeyboardMarkup:
    items = shopping_list["items"]

    buttons = []

    # Спочатку невиконані, потім куплені.
    indices = (
        [i for i, item in enumerate(items) if not item["done"]]
        + [i for i, item in enumerate(items) if item["done"]]
    )

    for idx in indices:
        item = items[idx]

        mark = "✅" if item["done"] else "⬜"
        text = f"{mark} {item['name']}"

        buttons.append(
            [
                InlineKeyboardButton(
                    text,
                    callback_data=f"toggle:{idx}",
                ),
                InlineKeyboardButton(
                    "❌",
                    callback_data=f"delete:{idx}",
                ),
            ]
        )

    if any(item["done"] for item in items):
        buttons.append(
            [
                InlineKeyboardButton(
                    "🧹 Очистити куплене",
                    callback_data="clear_completed",
                )
            ]
        )

    buttons.append(
        [
            InlineKeyboardButton(
                "➕ Додати товар",
                callback_data="add_mode",
            )
        ]
    )

    buttons.append(
        [
            InlineKeyboardButton(
                "📤 Поділитися списком",
                callback_data="share_code",
            )
        ]
    )

    buttons.append(
        [
            InlineKeyboardButton(
                "🏠 Меню",
                callback_data="home",
            )
        ]
    )

    return InlineKeyboardMarkup(buttons)


# ---------- Відображення списку ----------

def render_text(shopping_list: dict) -> str:
    items = shopping_list["items"]
    members_count = len(shopping_list["members"])

    active = [
        item for item in items
        if not item["done"]
    ]

    completed = [
        item for item in items
        if item["done"]
    ]

    lines = [
        "🛒 СПІЛЬНИЙ СПИСОК",
        "",
    ]

    if active:
        lines.append("📌 Потрібно купити:")

        for item in active:
            lines.append(
                f"⬜ {item['name']}"
            )

    if completed:
        lines.append("")
        lines.append("✅ Куплено:")

        for item in completed:
            lines.append(
                f"☑️ {item['name']}"
            )

    if not items:
        lines.append("✨ Список поки порожній.")

    lines.extend(
        [
            "",
            f"📊 Всього: {len(items)} | "
            f"Куплено: {len(completed)}",
            f"👥 Учасники: {members_count}/{MAX_MEMBERS}",
            f"🔑 Код: {shopping_list['invite_code']}",
        ]
    )

    return "\n".join(lines)


# ---------- Синхронізація ----------

async def sync_list(
    context: ContextTypes.DEFAULT_TYPE,
    list_id: str,
) -> None:
    data = load_data()
    shopping_list = data["lists"].get(list_id)

    if not shopping_list:
        return

    text = render_text(shopping_list)
    keyboard = build_keyboard(shopping_list)

    for chat_id in shopping_list["members"]:
        message_id = shopping_list["messages"].get(chat_id)

        if message_id:
            try:
                await context.bot.edit_message_text(
                    chat_id=int(chat_id),
                    message_id=int(message_id),
                    text=text,
                    reply_markup=keyboard,
                )
                continue

            except TelegramError:
                # Старе повідомлення могло бути видалене.
                pass

        try:
            message = await context.bot.send_message(
                chat_id=int(chat_id),
                text=text,
                reply_markup=keyboard,
            )

            shopping_list["messages"][chat_id] = message.message_id

        except TelegramError as error:
            logger.error(
                "Не вдалося оновити чат %s: %s",
                chat_id,
                error,
            )

    save_data(data)


# ---------- /start ----------

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    chat_id = str(update.effective_chat.id)

    context.user_data.pop("awaiting_item", None)
    context.user_data.pop("awaiting_join_code", None)

    data = load_data()
    list_id = get_user_list_id(data, chat_id)

    if list_id and list_id in data["lists"]:
        await sync_list(context, list_id)
        return

    await update.message.reply_text(
        "🛒 Привіт!\n\n"
        "Це спільний список покупок.\n"
        "Ти можеш створити власний список "
        "або приєднатися до списку іншої людини.",
        reply_markup=main_menu_keyboard(),
    )


# ---------- Додавання ----------

async def add_item_to_list(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
) -> None:
    chat_id = str(update.effective_chat.id)

    data = load_data()
    list_id = get_user_list_id(data, chat_id)

    if not list_id or list_id not in data["lists"]:
        await update.message.reply_text(
            "Спочатку створи або приєднайся до спільного списку.",
            reply_markup=main_menu_keyboard(),
        )
        return

    text = text.strip()

    if not text:
        return

    shopping_list = data["lists"][list_id]

    shopping_list["items"].append(
        {
            "name": text,
            "done": False,
        }
    )

    save_data(data)

    await sync_list(context, list_id)

    await update.message.reply_text(
        f"✅ Додано: {text}"
    )


async def add_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    text = " ".join(context.args).strip()

    if text:
        await add_item_to_list(
            update,
            context,
            text,
        )
        return

    context.user_data["awaiting_item"] = True

    await update.message.reply_text(
        "➕ Напиши назву товару:"
    )


# ---------- Список ----------

async def list_items(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    chat_id = str(update.effective_chat.id)

    data = load_data()
    list_id = get_user_list_id(data, chat_id)

    if not list_id or list_id not in data["lists"]:
        await update.message.reply_text(
            "У тебе ще немає спільного списку.",
            reply_markup=main_menu_keyboard(),
        )
        return

    await sync_list(context, list_id)


# ---------- Очистити все ----------

async def clear_list(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    chat_id = str(update.effective_chat.id)

    data = load_data()
    list_id = get_user_list_id(data, chat_id)

    if not list_id or list_id not in data["lists"]:
        return

    data["lists"][list_id]["items"] = []

    save_data(data)

    await sync_list(context, list_id)


# ---------- Callback-кнопки ----------

async def button_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    query = update.callback_query
    chat_id = str(update.effective_chat.id)

    await query.answer()

    data = load_data()
    list_id = get_user_list_id(data, chat_id)


    # Скасувати поточну дію
    if query.data == "cancel_action":
        context.user_data.pop("awaiting_item", None)
        context.user_data.pop("awaiting_join_code", None)

        if list_id and list_id in data["lists"]:
            await sync_list(context, list_id)
        else:
            await query.message.reply_text(
                "🏠 Головне меню:",
                reply_markup=main_menu_keyboard(),
            )

        return

    # Створити список
    if query.data == "create_list":
        if list_id and list_id in data["lists"]:
            await sync_list(context, list_id)
            return

        list_id = create_list(data, chat_id)
        save_data(data)

        await sync_list(context, list_id)
        return

    # Приєднатися
    if query.data == "join_mode":
        context.user_data["awaiting_join_code"] = True
        context.user_data.pop("awaiting_item", None)

        await query.message.reply_text(
            "🔗 Введи 6-значний код списку:",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "❌ Скасувати",
                            callback_data="cancel_action",
                        )
                    ]
                ]
            ),
        )
        return

    # Додати товар
    if query.data == "add_mode":
        if not list_id or list_id not in data["lists"]:
            await query.message.reply_text(
                "Спочатку створи або приєднайся до списку.",
                reply_markup=main_menu_keyboard(),
            )
            return

        context.user_data["awaiting_item"] = True
        context.user_data.pop("awaiting_join_code", None)

        await query.message.reply_text(
            "➕ Напиши назву товару:",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "❌ Скасувати",
                            callback_data="cancel_action",
                        )
                    ]
                ]
            ),
        )
        return

    # Показати список
    if query.data == "show_list":
        if list_id and list_id in data["lists"]:
            await sync_list(context, list_id)
        else:
            await query.message.reply_text(
                "Спочатку створи або приєднайся до списку.",
                reply_markup=main_menu_keyboard(),
            )
        return

    # Код списку
    if query.data == "share_code":
        if list_id and list_id in data["lists"]:
            code = data["lists"][list_id]["invite_code"]

            await query.message.reply_text(
                "📤 Поділитися списком\n\n"
                f"`{code}`\n\n"
                "Передай цей код другій людині, "
                "щоб вона могла приєднатися."
            )
        return

    # Меню
    if query.data == "home":
        if list_id and list_id in data["lists"]:
            await sync_list(context, list_id)
        else:
            await query.message.reply_text(
                "🛒 Головне меню:",
                reply_markup=main_menu_keyboard(),
            )
        return

    # Якщо користувач ще не має списку
    if not list_id or list_id not in data["lists"]:
        await query.message.reply_text(
            "Спочатку створи або приєднайся до списку.",
            reply_markup=main_menu_keyboard(),
        )
        return

    shopping_list = data["lists"][list_id]

    # Очистити куплене
    if query.data == "clear_completed":
        shopping_list["items"] = [
            item
            for item in shopping_list["items"]
            if not item["done"]
        ]

        save_data(data)
        await sync_list(context, list_id)
        return

    # Checkbox / Delete
    action, _, arg = query.data.partition(":")

    if action == "toggle":
        idx = int(arg)

        if 0 <= idx < len(shopping_list["items"]):
            item = shopping_list["items"][idx]
            item["done"] = not item["done"]

    elif action == "delete":
        idx = int(arg)

        if 0 <= idx < len(shopping_list["items"]):
            shopping_list["items"].pop(idx)

    save_data(data)

    await sync_list(context, list_id)


# ---------- Звичайний текст ----------

async def unknown_text(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    text = update.message.text.strip()

    if not text:
        return

    # Очікуємо код списку
    if context.user_data.get("awaiting_join_code"):
        context.user_data.pop("awaiting_join_code", None)

        chat_id = str(update.effective_chat.id)

        data = load_data()
        code = text.upper()

        list_id = find_list_by_code(data, code)

        if not list_id:
            await update.message.reply_text(
                "❌ Список із таким кодом не знайдено.\n\n"
                "Перевір код і спробуй ще раз."
            )
            return

        shopping_list = data["lists"][list_id]

        if chat_id in shopping_list["members"]:
            data["users"][chat_id] = list_id
            save_data(data)

            await sync_list(context, list_id)
            return

        if len(shopping_list["members"]) >= MAX_MEMBERS:
            await update.message.reply_text(
                "❌ Цей список уже має двох учасників."
            )
            return

        old_list_id = data["users"].get(chat_id)

        if old_list_id and old_list_id in data["lists"]:
            await update.message.reply_text(
                "❌ Ти вже приєднаний до іншого списку.\n"
                "Спочатку використай окремий список."
            )
            return

        shopping_list["members"].append(chat_id)
        data["users"][chat_id] = list_id

        save_data(data)

        await sync_list(context, list_id)

        await update.message.reply_text(
            "✅ Ти приєднався до спільного списку!"
        )

        return

    # Очікуємо товар
    if context.user_data.get("awaiting_item"):
        context.user_data.pop("awaiting_item", None)

        await add_item_to_list(
            update,
            context,
            text,
        )
        return

    # Якщо список вже існує —
    # звичайний текст вважаємо новим товаром.
    chat_id = str(update.effective_chat.id)

    data = load_data()
    list_id = get_user_list_id(data, chat_id)

    if list_id and list_id in data["lists"]:
        await add_item_to_list(
            update,
            context,
            text,
        )
        return

    await update.message.reply_text(
        "Спочатку створи або приєднайся до спільного списку.",
        reply_markup=main_menu_keyboard(),
    )


# ---------- Запуск ----------

def main() -> None:
    if not BOT_TOKEN:
        raise RuntimeError(
            "Не знайдено BOT_TOKEN. Створи файл .env "
            "і додай токен від @BotFather."
        )

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(
        CommandHandler("start", start)
    )

    app.add_handler(
        CommandHandler("add", add_command)
    )

    app.add_handler(
        CommandHandler("list", list_items)
    )

    app.add_handler(
        CommandHandler("clear", clear_list)
    )

    app.add_handler(
        CallbackQueryHandler(button_handler)
    )

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            unknown_text,
        )
    )

    logger.info("Shared Shopping List Bot запущено...")

    app.run_polling()


if __name__ == "__main__":
    main()
