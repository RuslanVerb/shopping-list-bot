# 🛒 Shopping List Bot

Простий Telegram-бот для списку покупок з чекбоксами (інлайн-кнопки).

## Можливості

- `/add <товар>` — додати пункт до списку
- `/list` — показати список з кнопками ✅/⬜
- `/clear` — очистити список
- Натискання на пункт перемикає його статус (куплено / не куплено)
- Кнопка ❌ видаляє конкретний пункт
- Дані зберігаються в `lists.json`, окремо для кожного чату

## Встановлення

1. Клонуй репозиторій:
   ```bash
   git clone https://github.com/<твій-нікнейм>/shopping-list-bot.git
   cd shopping-list-bot
   ```

2. Створи віртуальне середовище і встанови залежності:
   ```bash
   python -m venv venv
   source venv/bin/activate   # Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. Отримай токен бота у [@BotFather](https://t.me/BotFather) (команда `/newbot`).

4. Скопіюй `.env.example` у `.env` і встав туди токен:
   ```bash
   cp .env.example .env
   ```

5. Запусти бота:
   ```bash
   python bot.py
   ```

## Технології

- Python 3.10+
- [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot) v21
