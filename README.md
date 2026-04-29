# JSON Truth Editor

UI для разметки эталонных JSON-файлов рядом с исходными документами заявок.
Используется как companion-tool к **TMS AI Test Runner** — здесь делается ручная
разметка ground_truth, который потом используется в `test_runner` как эталон
для оценки качества AI-extraction.

## Что нового

- Светлая тема, согласованная по стилю с **TMS AI Test Runner** (`server.py`).
- Form Editor знает Stage 2-схему (`isComplexRoute / points[] с inline containers
  / from / to / контейнерные поля`) — можно добавлять/удалять/перемещать точки и контейнеры
  кнопками.
- Раздельные поля для каждой точки и каждого inline-контейнера.
- Auto re-label A / 1 / 2 / … / Б при добавлении/перемещении точек.
- Кнопка **Проверить шейп** — валидатор Stage 2: подсветит несоответствия типов
  (pickup_loaded/load/dropoff_loaded/return_empty/...), enum-значений
  (HC/DC/RF, 20'/40'/40'HC/45'HC, loaded/empty), несовпадение fromAddress/toAddress
  с первой/последней точкой, проблемы isComplexRoute vs points/containers и т.д.
- Шаблоны быстрой вставки: `+ Complex` (3 точки), `+ Simple` (from/to + global containers).
- Прогресс-бар сверху: **N/M verified** + индикатор «не сохранено / сохранено».
- Фильтр пар по имени + переключатели «Все / Ждут / Готовы».
- Ctrl+S — сохранение, Alt+↑/↓ — переход к prev/next паре, Esc — закрыть модалы.
- Drag-and-drop в окне загрузки.
- DOCX preview больше не тёмный.

## Возможности

- **Массовая загрузка**: один input принимает любую смесь документов и JSON.
  Пары спариваются по совпадению имени без расширения:
  `001.pdf` + `001.json`, `order_42.docx` + `order_42.json`.
- **Предпросмотр** в левой панели:
  - PDF — нативный iframe
  - DOCX/DOC — конверсия в HTML через mammoth (DOC → DOCX через LibreOffice headless)
  - TXT — plain text monospace
- **Form Editor** (правая панель, режим «Форма»):
  - Канонические поля: `isComplexRoute / from / to`
  - Точки маршрута с цветовой меткой типа (pickup_loaded / load / wash / dropoff_loaded / return_empty / …)
  - Inline-контейнеры внутри каждой точки (для complex-mode)
  - Глобальные `containers[]` для simple-mode
  - Legacy-поля: `fromAddress / toAddress / pickupDate / pickupTime / deliveryDate / deliveryTime / contacts / comments`
- **JSON Raw** (вкладка «JSON Raw») — для быстрых правок руками; live-валидация JSON.
- **Verify** — пометка пары как готовой; в списке слева видно ✓ verified.
- **Удаление** — отдельной пары или всех сразу.
- Docker-ready (`Dockerfile` + `docker-compose.yml`), не-root user, security headers, CSP.

## Команды для запуска

### Через Docker Compose (рекомендуемый путь)

```bash
cd C:\Users\maxim\PycharmProjects\D\json-truth-editor
docker-compose up --build -d
```

Открой: **http://localhost:8002**

Логи / остановка / пересборка:
```bash
docker-compose logs -f editor
docker-compose down
docker-compose up --build -d   # пересобрать после правок кода
```

Если правил только `static/index.html` — достаточно:
```bash
docker cp static/index.html json-truth-editor:/app/static/index.html
```
(контейнер сразу подхватит — index.html читается на каждом GET `/`).

Если правил `app/*.py` — нужен `docker-compose up --build -d`.

### Локально без Docker (для разработки)

```bash
cd C:\Users\maxim\PycharmProjects\D\json-truth-editor
python -m venv .venv
.venv\Scripts\activate           # Windows
# source .venv/bin/activate      # Mac/Linux
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Открой: **http://localhost:8000**

> Локально DOC→DOCX конверсия требует установленный LibreOffice headless в PATH;
> без него `.doc`-файлы загрузятся, но без предпросмотра — оригинал доступен через
> «↓ Скачать».

### Полная очистка данных

Данные хранятся в Docker-volume `editor-data` (через docker-compose) или в `./data/`
при локальном запуске.

```bash
# через UI
# Заголовок → "Очистить всё"

# через CLI
docker-compose down -v          # удалить volume
rm -rf data/                    # локально
```

## Структура проекта

```
json-truth-editor/
├── app/
│   ├── main.py                  — FastAPI, security middleware, /, /health
│   └── routers/pairs.py         — REST API: pairs, batch upload, verify, schema templates
├── static/index.html            — SPA (Form/Raw editor, light theme как TMS Test Runner)
├── k8s/deployment.yaml          — Kubernetes-манифест (если нужен deploy в кластер)
├── Dockerfile
├── docker-compose.yml           — порт 8002→8000, volume editor-data
└── requirements.txt
```

## API

| Метод   | Эндпоинт                          | Описание                                  |
|---------|-----------------------------------|-------------------------------------------|
| POST    | `/api/pairs/batch`                | Массовая загрузка (multipart `files=…`)   |
| POST    | `/api/pairs`                      | Загрузить одну пару                       |
| GET     | `/api/pairs`                      | Список всех пар                           |
| GET     | `/api/pairs/{id}`                 | Метаданные пары                           |
| GET     | `/api/pairs/{id}/document`        | Предпросмотр документа (PDF/HTML/TXT)     |
| GET     | `/api/pairs/{id}/original`        | Скачать оригинал                          |
| GET     | `/api/pairs/{id}/json`            | Получить эталонный JSON                   |
| PUT     | `/api/pairs/{id}/json`            | Сохранить JSON (Ctrl+S из UI)             |
| PATCH   | `/api/pairs/{id}/verify`          | Toggle флаг verified                      |
| DELETE  | `/api/pairs/{id}`                 | Удалить пару                              |
| DELETE  | `/api/pairs`                      | Удалить ВСЕ пары                          |
| GET     | `/api/schema/template/{kind}`     | Шаблон пустого объекта Stage 2 (`container`/`point`/`complex`/`simple`) |
| GET     | `/api/schema/enums`               | Допустимые значения enum-полей            |
| GET     | `/health`                         | Healthcheck (для Docker / k8s)            |

## Stage 2 schema (что редактируем)

Главный JSON, который размечаем здесь:

```json
{
  "isComplexRoute": true,
  "from": null, "to": null,
  "containers": null,
  "points": [
    {
      "order": 1, "label": "A",
      "type": "pickup_loaded",
      "address": "ст. Владивосток",
      "date": null, "time": null,
      "contacts": "Павлов Виталий +7 905 082 1414",
      "comment": "Получение гружёного контейнера с ЖД",
      "containers": [
        { "containerNumber": "TCNU7305809", "containerType": null,
          "containerSize": null, "isUnnumbered": false,
          "status": "loaded", "cargoWeight": 20000,
          "pinCode": null, "comment": "Крупа 503107" }
      ]
    }
  ],
  "fromAddress": "ст. Владивосток",
  "toAddress": "ст. Владивосток",
  "pickupDate": null, "pickupTime": null,
  "deliveryDate": null, "deliveryTime": null,
  "contacts": "Павлов …; Александр …",
  "comments": "Станция отправления по ЖД: Новосибирск-Восточный."
}
```

- **Complex mode**: `isComplexRoute=true`, `points[]` с inline-контейнерами,
  top-level `containers=null`, `from=null`, `to=null`.
- **Simple mode**: `isComplexRoute=false`, `containers[]` глобально,
  `from/to` строки, `points=null`.
- Legacy-поля (`fromAddress / toAddress / pickupDate / …`) автоматически
  выводятся из канонической структуры в основном pipeline (см.
  `tms-ai-module/app/ai_service.py::_finalize`).

## Безопасность

- Security headers (CSP, X-Frame-Options, X-Content-Type-Options, Referrer-Policy)
- Лимит размера загрузки (`MAX_UPLOAD_MB`, по умолчанию 50)
- Non-root пользователь в контейнере (`editor:editor`)
- Валидация расширений и JSON
- UUID-based хранение (защита от path traversal)
- Swagger/OpenAPI отключены в проде

## Деплой в Kubernetes

См. `k8s/deployment.yaml`. Образ собирается из `Dockerfile`.
