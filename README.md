# NHL Telegram Card Bot — стартовый каркас

## Что уже готово

- запуск бота через `main.py`;
- переменные окружения через `.env`;
- `BOT_TOKEN` из env;
- `ADMIN_IDS` через запятую;
- команда `/start`;
- отдельная reply-клавиатура пользователя;
- отдельная reply-клавиатура администратора;
- заглушки под все основные разделы;
- Inline-кнопка возврата в главное меню;
- структура под будущие модули, БД и Railway.

## Как запустить локально

1. Создайте `.env` из примера:

```powershell
Copy-Item .env.example .env
```

2. Заполните `.env`:

```env
BOT_TOKEN=токен_бота
ADMIN_IDS=123456789,987654321
```

3. Установите зависимости:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

4. Запустите бота:

```powershell
python main.py
```

## Railway

В Railway нужно добавить переменные:

```env
BOT_TOKEN=токен_бота
ADMIN_IDS=123456789,987654321
```

Команда запуска уже указана в `railway.json`:

```bash
python main.py
```
