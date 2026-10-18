# 📝 B2B Checklist & TechCards REST API

[![Python Version](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://www.python.org/)
[![Django](https://img.shields.io/badge/Django-5.x-092E20.svg?logo=django)](https://www.djangoproject.com/)
[![DRF](https://img.shields.io/badge/DRF-3.x-red.svg)](https://www.django-rest-framework.org/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15%2B-336791.svg?logo=postgresql)](https://www.postgresql.org/)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED.svg?logo=docker)](https://www.docker.com/)

Современный REST API микросервис для управления производственными процессами: динамическими шаблонами чек-листов (осмотр, приемка, сдача оборудования) и **технологическими картами настроек рабочих центров**. 
Проект построен на принципах **Clean Architecture**, **SOLID**, использует **EAV (Entity-Attribute-Value)** для форм анкетирования и **древовидную нормализованную структуру** для тех. карт.

## ✨ Ключевые архитектурные решения и фичи

*   **Изолированный Сервисный слой:** Вся бизнес-логика (транзакции, версионирование, вычисление статусов) вынесена в сервисы. Вьюсеты отвечают только за роутинг, а админка закрыта на Read-Only для защиты от некорректных мутаций.
*   **Строгое версионирование (Append-Only):** В домене тех. карт отключены методы `PUT/PATCH`. Любое изменение настроек станка создает новую версию (v+1) и архивирует предыдущую. При случайном удалении актуальной карты происходит автоматический `Rollback` на предыдущую версию.
*   **Защита от JSON-бомб (Memory Exhaustion):** API на лету обходит графы и валидирует глубину рекурсии и количество узлов перед обращением к БД.
*   **Динамическая валидация (EAV):** Типы полей для чек-листов, их обязательность и значения по умолчанию определяются в шаблонах. API "на лету" валидирует присылаемые ответы.
*   **Движок правил (Rule Engine):** Фронтенд задает правила в JSON, а Бэкенд автоматически анализирует ответы и проставляет метки `is_violation` (отклонения/поломки).
*   **Файлы и Вложения:** Возможность прикреплять фотографии дефектов и документы (`multipart/form-data`).

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
3. Запустите контейнеры:
   ```bash
   docker-compose -f docker-compose.yml up -d --build
   ```
*(Миграции и сборка статики выполнятся автоматически через Init-контейнер).*

### Способ 2: Локальный запуск (Разработка)

1. Клонируйте репозиторий и перейдите в папку `src`:
   ```
   git clone https://github.com/LLC-Polipak/ChecklistsAPI.git
   cd src
   ```
2. Настройте окружение и запустите:
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

Интерактивная документация Swagger / OpenAPI 3.0 доступна по адресу: 👉 `api/v1/docs/`

### ⚙️ Домен Технологических карт (Tech Cards)

*API работает в парадигме Immutable Data (Неизменяемых данных).*

| Метод    | URL                               | Описание                                                               |
|:---------|:----------------------------------|:-----------------------------------------------------------------------|
| `GET`    | `/api/v1/tech-cards/`             | Список актуальных карт (фильтры: `?equipment_uid=`, `?is_archived=`) |
| `POST`   | `/api/v1/tech-cards/`             | Добавить карту (авто-архивирует предыдущую и создает `v+1`)            |
| `GET`    | `/api/v1/tech-cards/{id}/`        | Получить древовидную структуру карты (разделы, параметры)              |
| `DELETE` | `/api/v1/tech-cards/{id}/`        | Soft Delete актуальной карты и автоматический `Rollback` на архивную   |

### 📋 Домен Шаблонов Чек-листов (Templates)

| Метод    | URL                               | Описание                                                   |
|:---------|:----------------------------------|:-----------------------------------------------------------|
| `GET`    | `/api/v1/templates/`              | Список актуальных шаблонов (с мощными фильтрами и поиском) |
| `POST`   | `/api/v1/templates/`              | Создать новый шаблон (вложенный JSON с группами и полями)  |
| `GET`    | `/api/v1/templates/{id}/`         | Получить структуру конкретного шаблона                     |
| `PUT`    | `/api/v1/templates/{id}/`         | Обновить шаблон (заменит старый, создаст новую версию)     |
| `DELETE` | `/api/v1/templates/{id}/`         | Удалить шаблон (с возможностью автоматического отката)     |

### 📝 Домен Анкет (Results)

| Метод    | URL                                  | Описание                                                   |
| :------- |:-------------------------------------|:-----------------------------------------------------------|
| `GET`    | `/api/v1/results/`                   | Список заполненных анкет (актуальные версии)               |
| `POST`   | `/api/v1/results/`                   | Отправить заполненную анкету (чистовик или черновик)       |
| `GET`    | `/api/v1/results/{id}/`              | Посмотреть ответы, комментарии и подписи конкретной анкеты |

*(Полный список эндпоинтов доменов Results и Attachments доступен в Swagger).*

---

## 💡 JSON Контракты (Payload)

В связи со сложной многоуровневой архитектурой, API принимает данные строго структурировано.

### Пример 1: Создание/Обновление Технологической карты (`POST /tech-cards/`)
*Отправка POST-запроса с теми же `equipment_uid` и `article` автоматически создаст новую версию.*
```json
{
  "equipment_uid": "FC-780",
  "article": "КРЫШКА 95008 ПРОЗРАЧНАЯ",
  "equipment_seq_num": "1",
  "sections": [
    {
      "name": "ДАННЫЕ ЦИКЛА ФОРМОВАНИЯ",
      "order": 1,
      "parameters": [
        {
          "name": "Время цикла",
          "value": "3.00",
          "unit": "сек.",
          "order": 1
        }
      ],
      "subsections": [
        {
          "name": "Формование",
          "order": 1,
          "parameters": [
            {
              "name": "Старт",
              "value": "1.40",
              "unit": "сек."
            }
          ]
        }
      ]
    }
  ]
}
```

### Пример 2: Сохранение анкеты чек-листа (`POST /results/`)
```json
{
  "equipment_uid": "EQ-FORKLIFT-01",
  "checklist_type": "HANDOVER",
  "user_uid": "USER-DRIVER-007",
  "shift_number": "DAY",
  "is_draft": false,
  "groups": [
    {
      "group_id": 1,
      "answers": [
        {
          "field_id": 101,
          "value": "7",
          "comment": "Проверено манометром"
        }
      ]
    }
  ]
}
```