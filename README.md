# SC2GG Bot v2 — Настройка и локальный запуск

Асинхронный Telegram-бот для анализа 1v1 реплеев StarCraft II (`.SC2Replay`), генерации PNG-карточек матчей, публикации компактных JSON-данных на GitHub и просмотра матчей в 2D-плеере Telegram Mini App (`viewer/`).

---

## 1. Предварительные требования

- **Python 3.12+** (в проекте используется `.venv` с Python 3.12.10)
- **Git** и аккаунт на **GitHub**
- **Telegram-бот** (токен от [@BotFather](https://t.me/BotFather))

---

## 2. Установка зависимостей

```powershell
# 1. Клонируйте репозиторий и перейдите в папку проекта
cd d:\Programming\sc2\sc2gg_bot

# 2. Если .venv ещё не создан (при использовании uv):
uv venv --python 3.12
uv pip install -e ".[dev]"

# Проверка окружения и автотестов:
.\.venv\Scripts\python.exe -m pytest
```

---

## 3. Настройка Telegram-бота и Mini App (@BotFather)

1. Откройте [@BotFather](https://t.me/BotFather) в Telegram.
2. Создайте нового бота (`/newbot`) или выберите существующего и скопируйте **BOT_TOKEN**.
3. Настройте Mini App для Direct Link кнопки `▶ Смотреть реплей`:
   - Выполните `/newapp` -> выберите вашего бота.
   - Укажите название и описание приложения.
   - В качестве **Web App URL** укажите адрес вашего GitHub Pages:
     `https://<username>.github.io/<repo>/`
   - Введите короткое имя **Short Name** (например, `replay`) — его нужно будет указать в `MINI_APP_SHORT_NAME`.
   - Итоговая кнопка в боте будет вести на `https://t.me/<bot_username>/<MINI_APP_SHORT_NAME>?startapp=<replay_id>`.

---

## 4. Настройка GitHub (Pages + Personal Access Token)

Бот загружает JSON-данные реплеев и миникарты в ветку `gh-pages` через GitHub Contents REST API, а GitHub Action [`.github/workflows/deploy-viewer.yml`](.github/workflows/deploy-viewer.yml) автоматически публикует `viewer/` и `icons/` в ту же ветку `gh-pages`, сохраняя папку `data/`.

1. **Включите GitHub Pages** в настройках репозитория (`Settings -> Pages`):
   - **Source:** `Deploy from a branch`
   - **Branch:** `gh-pages` / `/ (root)`
2. **Запустите первый деплой фронтенда:**
   - После пуша в `master` (или вручную через вкладку `Actions -> Deploy Mini App Viewer -> Run workflow`) создастся ветка `gh-pages` с содержимым `viewer/` и `icons/`.
3. **Создайте GitHub Token** для бота (`Settings -> Developer settings -> Personal access tokens -> Fine-grained tokens`):
   - **Repository access:** `Only select repositories` -> выберите ваш репозиторий.
   - **Permissions -> Repository permissions -> Contents:** `Read and write`.
   - Скопируйте токен в `GITHUB_TOKEN`.

---

## 5. Конфигурация `.env`

Скопируйте `.env.example` в `.env` и заполните переменные:

```env
DEBUG=false

# Telegram Bot
BOT_TOKEN=123456:ABC-DEF...
MINI_APP_URL=https://<username>.github.io/<repo>/
MINI_APP_SHORT_NAME=replay

# GitHub REST API Storage
GITHUB_TOKEN=github_pat_...
GITHUB_REPO=<username>/<repo>
GITHUB_BRANCH=gh-pages
GITHUB_DATA_PREFIX=data

# Локальная директория (SQLite-кэш, PNG-карточки, временные файлы)
DATA_DIR=./data

# Опционально (для Этапа 6)
BLIZZARD_CLIENT_ID=
BLIZZARD_CLIENT_SECRET=
YOUTUBE_API_KEY=
```

> **Примечание:** если `MINI_APP_SHORT_NAME` оставить пустым, бот будет формировать прямую внешнюю ссылку вида `https://<username>.github.io/<repo>/?startapp=<replay_id>`, которая тоже работает в `viewer/`.

---

## 6. Как локально запустить и протестировать весь флоу

### Вариант A: Полный локальный тест без GitHub и Telegram (офлайн)

Позволяет проверить парсер, генерацию JSON/миникарты и 2D-плеер `viewer/` прямо в браузере:

1. **Сгенерируйте JSON и миникарту из тестового реплея (`files/*.SC2Replay`):**
   ```powershell
   .\.venv\Scripts\python.exe -c "from pathlib import Path; from app.parser.replay_parser import parse_replay_file; p = next(Path('files').glob('*.SC2Replay')); b = parse_replay_file(p); Path('data/replays').mkdir(parents=True, exist_ok=True); Path('data/minimaps').mkdir(parents=True, exist_ok=True); (Path('data/replays') / f'{b.data.meta.replay_id}.json').write_text(b.data.model_dump_json(), encoding='utf-8'); (Path('data/minimaps') / b.data.meta.minimap_filename).write_bytes(b.minimap_png) if b.minimap_png else None; print('REPLAY_ID:', b.data.meta.replay_id)"
   ```
   Команда выведет `REPLAY_ID: <id>` (например, `43c30f042c96`).

2. **Запустите локальный HTTP-сервер из корня проекта:**
   ```powershell
   .\.venv\Scripts\python.exe -m http.server 8765 --bind 127.0.0.1
   ```

3. **Откройте плеер в браузере:**
   `http://127.0.0.1:8765/viewer/?startapp=<id>`

   Проверьте:
   - отображение миникарты и выравнивание баз/юнитов;
   - плавное воспроизведение (`▶`), переключение скоростей `1x–8x`, зум/пан;
   - вкладки **Карта**, **Билд**, **Графики**, **Битвы** (кнопка `▶ На карте`).

---

### Вариант B: Полный End-to-End тест с реальным Telegram-ботом и GitHub Pages

1. Убедитесь, что `.env` заполнен (`BOT_TOKEN`, `MINI_APP_URL`, `MINI_APP_SHORT_NAME`, `GITHUB_TOKEN`, `GITHUB_REPO`), а `viewer/` задеплоен на `gh-pages`.
2. Запустите бота локально:
   ```powershell
   .\.venv\Scripts\python.exe -m app.main
   ```
3. Отправьте боту в Telegram команду `/start`, затем перешлите любой `.SC2Replay` файл из папки `files/`.
4. **Ожидаемый результат:**
   - Бот ответит `⏳ Анализирую реплей...`, затем удалит статус и пришлёт PNG-карточку матча со сводкой и кнопкой `▶ Смотреть реплей`.
   - При повторной отправке того же `.SC2Replay` бот мгновенно отдаст кэшированный результат из SQLite (`data/bot.sqlite`) без повторного парсинга и загрузки на GitHub.
   - По нажатию на кнопку `▶ Смотреть реплей` внутри Telegram откроется Mini App с 2D-плеером. Если GitHub Pages ещё не успел пересобраться после коммита, плеер автоматически подгрузит JSON и миникарту через fallback `raw.githubusercontent.com`.

---

## 7. Автотесты

Запуск всего набора unit- и интеграционных тестов (парсер, рендерер PNG, GitHub API storage, хендлеры бота, SQLite):

```powershell
.\.venv\Scripts\python.exe -m pytest
```
