# План разработки SC2GG Bot v2 (Clean Architecture + Monorepo)

> **Инструкция для нового диалога:**
> 1. Прочитай только этот файл (`PLAN.md`) и файлы, относящиеся к текущему невыполненному этапу. Не сканируй весь репозиторий без необходимости.
> 2. Все команды Python выполняй через виртуальное окружение: `.\.venv\Scripts\python.exe` (Python 3.12.10, Windows 11).
> 3. Выполняй **один этап за раз** (или часть этапа), проверяй результат тестом/запуском.
> 4. Соблюдай принципы: код в репозитории полностью обезличен (12-Factor, секреты/ID/URL только в `.env`), чистые слои (`domain/` → `parser/` / `storage/` / `renderer/` → `bot/`).
> 5. После завершения этапа отметь `[x]` в чеклисте и обнови блок **«Текущий статус»**.

---

## Текущий статус
- **Активный этап:** Этап 6 (Дополнительные модули: стримы и Blizzard MMR)
- **Ветки Git:** `v1` (архив старого бота `84ecd7b`), `master` (чистая разработка `v2`)
- **Окружение:** `.venv` (`Python 3.12.10`), зависимости установлены (`aiogram 3.32.0`, `pydantic-settings 2.16.3`, `sc2reader 1.9.0`, `pillow 13.0.0`, `matplotlib 3.11.2`, `aiosqlite 0.22.1`, `httpx 0.28.1`, `pytest 9.2.0`)
- **Конфигурация:** обезличенный 12-Factor [`app/config.py`](app/config.py) + `.env.example` + локальный `.env` (в `.gitignore`)
- **Тестовые реплеи:** `files/*.SC2Replay`
- **Фронтенд Mini App:** реализован в [`viewer/`](viewer/) и деплоится на `gh-pages` через [`.github/workflows/deploy-viewer.yml`](.github/workflows/deploy-viewer.yml); JSON-данные реплеев публикуются через GitHub REST API (`GITHUB_REPO` / `GITHUB_BRANCH` / `GITHUB_DATA_PREFIX`).

---

## Этапы

### [x] Этап 0 и 1. Аудит, окружение и чистый 12-Factor каркас
- [x] Старый бот заархивирован в ветку `v1`, `master` очищен под `v2`.
- [x] Создан `.venv` (Python 3.12.10), установлен `pyproject.toml` и пакеты через `uv`.
- [x] Настроен обезличенный `app/config.py` (12-Factor) и `.env.example` / `.env`.
- [x] Проверен импорт `app.config`, `aiogram`, `sc2reader` и парсинг тестового реплея.

---

### [x] Этап 2. Доменная модель и парсер реплеев (`app/domain/` + `app/parser/`)
**Цель:** отделить бизнес-данные от `sc2reader` и получать компактный, точный JSON для 2D-плеера и PNG-карточки.
- [x] Создать `app/domain/models.py` (Pydantic-модели: `ReplayData`, `MatchMeta`, `PlayerInfo`, `TimelineFrame`, `BattleEvent`, `BuildOrderItem`, `ChartSeries`).
- [x] Реализовать `app/parser/replay_parser.py` (запуск в `asyncio.to_thread`):
  - валидация 1v1 + вычисление `sha256` файла для дедупликации;
  - корректная обработка морфов (дрон → здание, яйцо зергов, фильтрация `Beacon*` и временных юнитов);
  - извлечение миникарты (`.tga` → `.png` в байтах) и словаря юнитов `unit_dict`;
  - сэмплирование позиций (шаг 3 сек) с keyframe + delta-кодированием для компактного JSON.
- [x] Реализовать `app/parser/battles.py`: кластеризация смертей юнитов в сражения и подсчёт потерь в минералах/газе.
- [x] Написать `tests/test_parser.py` на реальных реплеях из `files/`.
- **Критерий готовности:** `pytest` проходит (`6 passed`); парсер превращает реплеи из `files/` в валидный JSON размером < 500 КБ. *(Проверено)*

---

### [x] Этап 3. Генератор PNG-карточки и GitHub REST API Storage
**Цель:** рендерить красивую инфографику для Telegram-чата и загружать JSON/миникарты на GitHub без локального `git push`.
- [x] Реализовать `app/renderer/summary_card.py` (`matplotlib` + `Pillow`): тёмная карточка матча с графиком армии/рабочих, расами, картой и победителем.
- [x] Реализовать интерфейс `app/storage/base.py` (`ReplayStorage`) и `app/storage/github_api.py` (асинхронный `httpx` клиент к GitHub Contents API `PUT /repos/{owner}/{repo}/contents/{path}` с проверкой, существует ли уже файл/миникарта).
- [x] Написать тесты с моком `httpx` для `GitHubApiStorage` и генерации PNG.
- **Критерий готовности:** `pytest` проходит (`12 passed`); генератор рендерит PNG-карточку на `files/10000 Feet LE (4).SC2Replay`, а `GitHubApiStorage` проверен тестами с `httpx.MockTransport`. *(Проверено)*

---

### [x] Этап 4. Telegram-бот (`app/bot/` + `app/db/`)
**Цель:** рабочий асинхронный бот на `aiogram 3.x` с кэшированием по SHA-256 и поддержкой групп.
- [x] Реализовать `app/db/repository.py` (`aiosqlite`): таблицы `replays` (`sha256`, `replay_id`, `map_name`, `created_at`) и `users`.
- [x] Реализовать `app/bot/handlers/start.py` и `app/bot/handlers/replays.py`:
  - при получении `.SC2Replay` проверяет `sha256` в БД (если уже был — сразу отдаёт результат без повторного парсинга);
  - отправляет PNG-карточку + текстовую сводку + Direct Link кнопку `▶ Смотреть реплей` (`https://t.me/<bot>/<app>?startapp=<replay_id>`).
- [x] Точка входа `app/main.py` с корректным graceful shutdown и логированием.
- **Критерий готовности:** `pytest` проходит (`17 passed`), диспетчер и роутеры `start` / `replays` собираются, обработка `.SC2Replay` и кэширование по SHA-256 проверены на реальном реплее `files/10000 Feet LE (4).SC2Replay`. *(Проверено)*

---

### [x] Этап 5. Фронтенд Telegram Mini App (`viewer/`) и автодеплой
**Цель:** красивый, плавный 2D-плеер в директории `viewer/` этого же репозитория с деплоем на GitHub Pages.
- [x] Создать `viewer/` (`index.html`, `styles.css`, `app.js`, `player.js`) + подключить иконки юнитов/рас из `icons/`.
- [x] Интеграция `telegram-web-app.js` (чтение `startapp`, тема Telegram).
- [x] Fallback-загрузка JSON: GitHub Pages URL → `raw.githubusercontent.com` (если GitHub Pages ещё пересобирается).
- [x] 2D-плеер на Canvas / PixiJS: интерполяция движения юнитов, зум/пан, маркеры битв на таймлайне, скорость `1x–8x`, вкладки *Карта / Билд-ордер / Графики / Битвы*.
- [x] Настроить `.github/workflows/deploy-viewer.yml` для автоматического деплоя `viewer/` + `icons/` на GitHub Pages.
- **Критерий готовности:** по кнопке из Telegram открывается Mini App и плавно воспроизводит реальный реплей. *(Проверено локально на `43c30f042c96` и `pytest` 17 passed)*

---

### [ ] Этап 6. Дополнительные модули (стримы и Blizzard MMR)
**Цель:** добавить мониторинг стримов и подтягивание MMR игроков.
- [ ] Фоновая задача мониторинга стримов через официальный YouTube Data API v3.
- [ ] Клиент Blizzard SC2 API (`client_id` / `client_secret`) для отображения MMR игроков.
