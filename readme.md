# 📝 B2B Checklist REST API

[![Python Version](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://www.python.org/)
[![Django](https://img.shields.io/badge/Django-5.x-092E20.svg?logo=django)](https://www.djangoproject.com/)
[![DRF](https://img.shields.io/badge/DRF-3.x-red.svg)](https://www.django-rest-framework.org/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15%2B-336791.svg?logo=postgresql)](https://www.postgresql.org/)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED.svg?logo=docker)](https://www.docker.com/)

Современный REST API для управления динамическими шаблонами чек-листов (осмотр, приемка, сдача оборудования) и сбора результатов анкетирования. Проект построен на принципах **Clean Architecture**, **SOLID** и использует **EAV (Entity-Attribute-Value)** паттерн для работы с динамическими формами.

## ✨ Ключевые архитектурные решения и фичи

*   **Динамическая валидация (EAV):** Типы полей (в т.ч. `DATE`, `RADIO`, `CHECKBOX`, `AUTO`), их обязательность и значения по умолчанию определяются в шаблонах. API "на лету" валидирует присылаемые ответы.
*   **Слой Сервисов и Кастомные QuerySets:** Бизнес-логика (транзакции, версионирование) изолирована в Service Layer. Взаимодействие с БД оптимизировано через "толстые" кастомные менеджеры с поддержкой цепочек (Chaining).
*   **Движок правил (Rule Engine):** Фронтенд может задавать правила в JSON-поле `metadata`. Бэкенд автоматически анализирует ответы и проставляет метки `is_violation` (отклонения/поломки).
*   **Документооборот (Workflow):** Поддержка черновиков (`is_draft`), рабочих смен и электронных подписей (`AUTHOR`, `READER`, `APPROVER`). Утверждение анкеты блокирует её от дальнейших изменений.
*   **Аудиторский след (Audit Trail):** Шаблоны и анкеты не перезаписываются при редактировании. Вместо этого они получают статус `is_deprecated=True`, и создается новая версия с привязкой к оригиналу.
*   **Экспорт и Отчеты (Builder Pattern):** Генерация печатных бланков в форматах **PDF** и **Excel** «на лету» с использованием паттерна "Строитель".
*   **Файлы и Вложения:** Возможность прикреплять фотографии дефектов и документы (`multipart/form-data`) к заполненным анкетам.

---

## 🚀 Установка и запуск

Проект полностью докеризован и готов к Production-развертыванию за Nginx.

### Способ 1: Docker Compose (Рекомендуемый)

1. Клонируйте репозиторий и перейдите в папку `infra`:
   ```bash
   git clone https://github.com/LLC-Polipak/ChecklistsAPI.git
   cd infra
   ```
2. Создайте файл `.env` на основе `.env.example`. (файл должен лежать в папке `infra`)
3. Положите файл шрифта `arial.ttf` в корень проекта (требуется для корректной генерации кириллицы в PDF).
4. Запустите контейнеры:
   ```bash
   docker-compose up --build -d
   ```
*(Миграции и сборка статики выполнятся автоматически через Init-контейнер).*

### Способ 2: Локальный запуск (Разработка)

1. Клонируйте репозиторий и перейдите в папку `src`:
   ```
   git clone https://github.com/LLC-Polipak/ChecklistsAPI.git
   cd src
   ```
2. Создайте файл `.env` на основе `.env.example`. (файл должен лежать в папке `src`)
3. Выполните следующие команды:
   ```bash
   python -m venv venv
   source venv/bin/activate  # Для Windows: venv\Scripts\activate
   pip install -r requirements.txt && pip install -r requirements.dev.txt
   python manage.py makemigrations
   python manage.py migrate
   python manage.py runserver
   ```

---

## 📡 REST API Endpoints

Интерактивная документация Swagger / OpenAPI 3.0 доступна по адресу после запуска сервера: 👉 `http://127.0.0.1:8000/api/docs/`

### 📋 Домен Шаблонов (Templates)

| Метод    | URL                            | Описание |
| :------- |:-------------------------------| :---------------------------------------------------------- |
| `GET`    | `/api/v1/templates/`           | Список актуальных шаблонов (с мощными фильтрами и поиском)  |
| `POST`   | `/api/v1/templates/`           | Создать новый шаблон (вложенный JSON с группами и полями)   |
| `GET`    | `/api/v1/templates/{id}/`         | Получить структуру конкретного шаблона                      |
| `PUT`    | `/api/v1/templates/{id}/`         | Обновить шаблон (заменит старый, создаст новую версию)      |
| `DELETE` | `/api/v1/templates/{id}/`         | Удалить шаблон (с возможностью автоматического отката)      |
| `GET`    | `/api/v1/templates/{id}/history/` | Посмотреть историю версий (оригинал и правки)               |

### 📝 Домен Анкет (Results)

| Метод    | URL                                  | Описание                                                 |
| :------- |:-------------------------------------| :------------------------------------------------------- |
| `GET`    | `/api/v1/results/`                      | Список заполненных анкет (актуальные версии)             |
| `POST`   | `/api/v1/results/`                      | Отправить заполненную анкету (чистовик или черновик)     |
| `GET`    | `/api/v1/results/{id}/`                 | Посмотреть ответы, комментарии и подписи конкретной анкеты|
| `PUT`    | `/api/v1/results/{id}/`                 | Внести исправления (создает новую версию анкеты)         |
| `DELETE` | `/api/v1/results/{id}/`                 | Удалить анкету                                           |
| `GET`    | `/api/v1/results/{id}/history/`         | История правок ответов в анкете                          |
| `POST`   | `/api/v1/results/{id}/sign/`            | Поставить электронную подпись (AUTHOR/READER/APPROVER)   |
| `POST`   | `/api/v1/results/{id}/upload_attachment/`| Прикрепить файл/фото к анкете (`multipart/form-data`)   |
| `GET`    | `/api/v1/results/{id}/export_excel/`    | Скачать анкету в формате печатного журнала (Excel)       |
| `GET`    | `/api/v1/results/{id}/export_pdf/`      | Скачать анкету в формате печатного журнала (PDF)         |

---

## 💡 JSON Контракт (Payload)

В связи со сложной многоуровневой архитектурой, API принимает данные строго структурировано.

**Пример сохранения анкеты (`POST /results/`):**

```json
{
  "equipment_uid": "EQ-FORKLIFT-01",
  "checklist_type": "HANDOVER",
  "user_uid": "USER-DRIVER-007",
  "shift_number": "DAY",
  "is_draft": false,
  "general_comment": "Смена сдана, замечаний по механике нет.",
  "groups": [
    {
      "group_id": 1,
      "answers": [
        {
          "field_id": 101,
          "value": "7",
          "comment": "Проверено манометром"
        },
        {
          "field_id": 102,
          "value": "true",
          "comment": ""
        }
      ]
    }
  ]
}
```