# 📝 B2B Checklist REST API

[![Python Version](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://www.python.org/)
[![Django](https://img.shields.io/badge/Django-5.x-092E20.svg?logo=django)](https://www.djangoproject.com/)
[![DRF](https://img.shields.io/badge/DRF-3.x-red.svg)](https://www.django-rest-framework.org/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15%2B-336791.svg?logo=postgresql)](https://www.postgresql.org/)

Современный REST API для управления динамическими шаблонами чек-листов (осмотр, приемка, сдача оборудования) и сбора результатов анкетирования. Проект построен на принципах **Clean Architecture**, **SOLID** и использует **EAV (Entity-Attribute-Value)** паттерн для работы с динамическими формами.

## ✨ Ключевые архитектурные решения

*   **Динамическая валидация (EAV):** Типы полей и их обязательность определяются пользователями в шаблонах. API "на лету" валидирует присылаемые ответы (проверяет приводимость строк к `INTEGER`, валидность булевых значений для `CHECKBOX` и соответствие спискам `CHOICE`).
*   **Иммутабельность и Версионирование (Audit Trail):** Шаблоны и заполненные анкеты не удаляются и не перезаписываются при редактировании. Вместо этого они получают статус `is_deprecated=True`, и создается новая версия с привязкой к оригиналу (`origin_id`). Это гарантирует строгий аудиторский след.
*   **Защита целостности данных:** Запрещено изменять шаблоны, по которым уже есть собранные результаты. Запрещено менять `UID` оборудования у существующих шаблонов.
*   **Оптимизация БД:** Решение проблемы N+1 с помощью `select_related` и `prefetch_related`. Использование `bulk_create` для массового сохранения ответов за один SQL-запрос. Транзакционность сложных операций (`@transaction.atomic`).

---

🚀 Установка и локальный запуск

1. Клонирование репозитория

git clone https://github.com/gevorgdjan/ChecklistsAPI.git
cd checklist-api

2. Создание виртуального окружения

python -m venv venv
# Активация (Windows)
venv\Scripts\activate
# Активация (Linux/Mac)
source venv/bin/activate

3. Установка зависимостей

pip install -r requirements.txt
pip install -r requirements.dev.txt

4. Настройка окружения

Создайте файл .env в корне проекта на основе .env.example.

5. Миграции и запуск

python manage.py makemigrations
python manage.py migrate
python manage.py createsuperuser  # Создание администратора
python manage.py runserver

📡 REST API Endpoints

Интерактивная документация Swagger / OpenAPI 3.0 доступна по адресу после
запуска сервера: 👉 http://127.0.0.1:8000/api/v1/docs/

📋 Домен Шаблонов (Templates)

| Метод    | URL                               | Описание
| :------- |:----------------------------------| :---------------------------------------------------------- |
| `GET`    | `/api/v1/templates/`              | Список актуальных шаблонов (с поддержкой фильтров)          |
| `POST`   | `/api/v1/templates/`              | Создать новый шаблон (вложенный JSON с полями)              |
| `GET`    | `/api/v1/templates/{id}/`         | Получить структуру конкретного шаблона                      |
| `PUT`    | `/api/v1/templates/{id}/`         | Обновить шаблон (заменит старый, создаст новую версию)      |
| `DELETE` | `/api/v1/templates/{id}/`         | Удалить шаблон (если по нему нет ответов)                   |
| `GET`    | `/api/v1/templates/{id}/history/` | Посмотреть историю версий (оригинал и правки)               |
| `GET`    | `/api/v1/templates/equipments/`   | Получить список уникальных `UID` оборудования для подсказок |

📝 Домен Анкет (Results)

| Метод    | URL                             | Описание                                                 |
| :------- |:--------------------------------| :------------------------------------------------------- |
| `GET`    | `/api/v1/results/`              | Список заполненных анкет (актуальные версии)             |
| `POST`   | `/api/v1/results/`              | Отправить заполненную анкету (с динамической валидацией) |
| `GET`    | `/api/v1/results/{id}/`         | Посмотреть ответы конкретной анкеты                      |
| `PUT`    | `/api/v1/results/{id}/`         | Внести исправления (создает новую версию анкеты)         |
| `DELETE` | `/api/v1/results/{id}/`         | Удалить анкету                                           |
| `GET`    | `/api/v1/results/{id}/history/` | История правок ответов в анкете                          |

💡 Примеры JSON (Контракт)

Пример отправки заполненной анкеты (POST /results/):

{
  "equipment_uid": "EQ-FORKLIFT-01",
  "checklist_type": "HANDOVER",
  "user_uid": "USER-DRIVER-007",
  "answers": {
    "1": "В норме",
    "2": "7",
    "3": "true"
  }
}
