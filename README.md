# JSON Truth Editor

Система для разметки и верификации JSON-файлов с предпросмотром исходных документов.

## Возможности

- **Массовая загрузка**: закиньте все документы и JSON файлы разом — пары создаются автоматически по совпадению имён (`order_1.pdf` + `order_1.json`)
- **Предпросмотр** документа (левая панель): PDF рендерится нативно, DOCX конвертируется в HTML через mammoth, TXT как текст
- **Редактор JSON** (правая панель) с переключением Form Editor ↔ JSON Raw
- **Сворачиваемая боковая панель** с списком пар
- **Верификация** (пометка проверенных пар)
- **Resizable панели**, Ctrl+S для быстрого сохранения
- Docker-ready, подготовлен для Kubernetes

## Быстрый старт

```bash
docker-compose up --build
# → http://localhost:8000
```

### Локально (для разработки)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

## Структура проекта

```
json-truth-editor/
├── app/
│   ├── main.py              # FastAPI, security middleware
│   └── routers/pairs.py     # API для пар документ+JSON
├── static/index.html         # SPA фронтенд
├── k8s/deployment.yaml       # Манифесты Kubernetes
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

## API

| Метод   | Эндпоинт                   | Описание                          |
|---------|----------------------------|-----------------------------------|
| POST    | /api/pairs/batch           | Массовая загрузка (multipart)     |
| POST    | /api/pairs                 | Загрузить одну пару               |
| GET     | /api/pairs                 | Список всех пар                   |
| GET     | /api/pairs/{id}/document   | Предпросмотр документа            |
| GET     | /api/pairs/{id}/original   | Скачать оригинал                  |
| GET     | /api/pairs/{id}/json       | Получить JSON                     |
| PUT     | /api/pairs/{id}/json       | Обновить JSON                     |
| PATCH   | /api/pairs/{id}/verify     | Переключить verified              |
| DELETE  | /api/pairs/{id}            | Удалить пару                      |

## Деплой в Kubernetes

1. Собрать и запушить образ в ваш registry
2. Обновить `image` в `k8s/deployment.yaml`
3. `kubectl apply -f k8s/deployment.yaml`

## Безопасность

- Security headers (CSP, X-Frame-Options, X-Content-Type-Options)
- Лимит размера загрузки (`MAX_UPLOAD_MB`, по умолчанию 50)
- Non-root пользователь в контейнере
- Валидация расширений и JSON
- Защита от path traversal (UUID-based хранение)
- Swagger/OpenAPI отключены
