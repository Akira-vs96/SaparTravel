# ER-модель базы данных SaparTravel

Модель построена по миграции `backend/migrations/versions/0001_initial.py` и
проверена по созданной PostgreSQL 17 базе в Docker.

## Диаграмма связей

```mermaid
erDiagram
    USERS ||--o{ EXPERIENCES : "publishes"
    DESTINATIONS ||--o{ EXPERIENCES : "contains"
    EXPERIENCES ||--o{ DEPARTURES : "has"
    USERS ||--o{ FAVORITES : "saves"
    EXPERIENCES ||--o{ FAVORITES : "is saved"
    USERS ||--o{ BOOKINGS : "creates"
    DEPARTURES ||--o{ BOOKINGS : "reserved in"
    BOOKINGS ||--o{ BOOKING_STATUS_HISTORY : "has"
    USERS ||--o{ BOOKING_STATUS_HISTORY : "changes"

    USERS {
        varchar36 id PK
        varchar120 name
        varchar254 email UK
        varchar255 password_hash
        varchar20 role
        boolean is_active
        timestamptz created_at
    }
    DESTINATIONS {
        varchar36 id PK
        varchar100 slug UK
        varchar160 name
        varchar160 name_en
        varchar160 name_kk
        varchar120 country
        varchar120 country_en
        varchar120 country_kk
        varchar30 continent
        text description
        text description_en
        text description_kk
        varchar2000 image_url
    }
    EXPERIENCES {
        varchar36 id PK
        varchar160 slug UK
        varchar36 vendor_id FK
        varchar36 destination_id FK
        varchar180 title
        varchar180 title_en
        varchar180 title_kk
        text description
        varchar30 category
        integer duration_days
        numeric12_2 price_from
        varchar3 currency
        numeric2_1 rating
        integer review_count
        boolean is_published
        json tags
        json included
        json excluded
        json itinerary
        timestamptz created_at
    }
    DEPARTURES {
        varchar36 id PK
        varchar36 experience_id FK
        date start_date
        date end_date
        integer capacity
        numeric12_2 price
        string UK_experience_start_date
    }
    FAVORITES {
        varchar36 user_id PK, FK
        varchar36 experience_id PK, FK
        timestamptz created_at
    }
    BOOKINGS {
        varchar36 id PK
        varchar20 reference UK
        varchar36 user_id FK
        varchar36 departure_id FK
        varchar20 status
        integer travelers_count
        numeric12_2 total_amount
        varchar3 currency
        varchar120 contact_name
        varchar254 contact_email
        text notes
        json experience_snapshot
        date start_date
        date end_date
        timestamptz created_at
    }
    BOOKING_STATUS_HISTORY {
        varchar36 id PK
        varchar36 booking_id FK
        varchar36 actor_id FK
        varchar20 status
        timestamptz created_at
    }
```

## Ключи и ограничения

| Таблица | Первичный ключ | Внешние ключи | Уникальность / проверки |
|---|---|---|---|
| `users` | `id` | — | `email`; роль `traveler/vendor/admin` |
| `destinations` | `id` | — | `slug`; индекс `continent` |
| `experiences` | `id` | `vendor_id → users.id`, `destination_id → destinations.id` | `slug`; длительность 1–90; цена ≥ 1; рейтинг 0–5 |
| `departures` | `id` | `experience_id → experiences.id` | `(experience_id, start_date)`; capacity 1–1000; end ≥ start |
| `favorites` | `(user_id, experience_id)` | `user_id → users.id`, `experience_id → experiences.id` | повторное избранное невозможно; удаление связи каскадное |
| `bookings` | `id` | `user_id → users.id`, `departure_id → departures.id` | `reference`; статус `pending/confirmed/cancelled/completed`; 1–20 путешественников |
| `booking_status_history` | `id` | `booking_id → bookings.id`, `actor_id → users.id` | история связывает бронь и пользователя, изменившего статус |

## Правило бронирования

При создании бронирования API блокирует строку `departures` через
`SELECT ... FOR UPDATE`, считает активные заявки и проверяет остаток мест.
Цена и итоговая сумма рассчитываются сервером. `experience_snapshot` сохраняет
условия тура на момент создания заявки, поэтому последующие изменения каталога
не меняют уже оформленную бронь.

## Фактическая проверка Docker PostgreSQL

На стенде создана база `sapartravel` в контейнере `postgres:17-alpine`.
Миграция `0001` применена, seed завершён без перезаписи существующих данных:

| Таблица | Записей |
|---|---:|
| `users` | 2 |
| `destinations` | 24 |
| `experiences` | 24 |
| `departures` | 72 |

Публичный локальный порт PostgreSQL — `127.0.0.1:55432`, потому что порт
`5432` уже был занят локальным экземпляром PostgreSQL. Внутри Docker-сети API
подключается к `db:5432`.

