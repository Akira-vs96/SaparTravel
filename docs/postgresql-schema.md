# Схема PostgreSQL и словарь полей

Актуальная схема: 36 таблиц, Alembic `0001 → 0002 → 0003 → 0004 → 0005`.
Проверки миграций: [журнал](verification-results.md). Обоснование 3НФ: [ER](er-model.md).

Деньги: `NUMERIC(12,2)`, API — строки Decimal. Моменты времени: UTC `TIMESTAMPTZ`;
даты поездок — `DATE` без преобразования полуночи. Отображение: Asia/Almaty.

Все поля без отметки NULL обязательны. Неперечисленные бизнес-ограничения обеспечивают транзакции.

## `categories`

| Поле | Тип | Ограничения |
|---|---|---|
| `code` | `VARCHAR(30)` | PK |
| `name_ru` | `VARCHAR(100)` | NOT NULL |
| `name_en` | `VARCHAR(100)` | NOT NULL |
| `name_kk` | `VARCHAR(100)` | NOT NULL |

## `demo_emails`

| Поле | Тип | Ограничения |
|---|---|---|
| `id` | `VARCHAR(36)` | PK |
| `recipient` | `VARCHAR(254)` | NOT NULL |
| `subject` | `VARCHAR(200)` | NOT NULL |
| `body` | `TEXT` | NOT NULL |
| `created_at` | `DATETIME` | NOT NULL |

Индексы: ix_demo_emails_created_at (created_at); ix_demo_emails_recipient (recipient).

## `destinations`

| Поле | Тип | Ограничения |
|---|---|---|
| `id` | `VARCHAR(36)` | PK |
| `slug` | `VARCHAR(100)` | UNIQUE |
| `continent` | `VARCHAR(30)` | NOT NULL |
| `image_url` | `VARCHAR(2000)` | NOT NULL |

UNIQUE `slug`.

Индексы: ix_destinations_continent (continent).

## `provider_operations`

| Поле | Тип | Ограничения |
|---|---|---|
| `id` | `VARCHAR(36)` | PK |
| `kind` | `VARCHAR(10)` | NOT NULL |
| `scenario` | `VARCHAR(40)` | NOT NULL |
| `status` | `VARCHAR(20)` | NOT NULL |
| `amount` | `NUMERIC(12, 2)` | NOT NULL |
| `currency` | `VARCHAR(3)` | NOT NULL |
| `created_at` | `DATETIME` | NOT NULL |

CHECK `amount >= 0`.

## `users`

| Поле | Тип | Ограничения |
|---|---|---|
| `id` | `VARCHAR(36)` | PK |
| `name` | `VARCHAR(120)` | NOT NULL |
| `email` | `VARCHAR(254)` | UNIQUE |
| `password_hash` | `VARCHAR(255)` | NOT NULL |
| `role` | `VARCHAR(20)` | NOT NULL |
| `is_active` | `BOOLEAN` | NOT NULL |
| `is_monitoring` | `BOOLEAN` | NOT NULL, default false; только явное provisioning |
| `created_at` | `DATETIME` | NOT NULL |

CHECK `role IN ('traveler', 'vendor', 'admin')`.

Индексы: UNIQUE ix_users_email (email).

## `audit_logs`

| Поле | Тип | Ограничения |
|---|---|---|
| `id` | `VARCHAR(36)` | PK |
| `actor_id` | `VARCHAR(36)` | NULL, FK → users.id |
| `action` | `VARCHAR(100)` | NOT NULL |
| `resource_type` | `VARCHAR(80)` | NOT NULL |
| `resource_id` | `VARCHAR(36)` | NULL |
| `details` | `JSON` | NOT NULL |
| `created_at` | `DATETIME` | NOT NULL |

Индексы: ix_audit_logs_created_at (created_at); ix_audit_logs_actor_id (actor_id).

## `destination_translations`

| Поле | Тип | Ограничения |
|---|---|---|
| `destination_id` | `VARCHAR(36)` | PK, FK → destinations.id / CASCADE |
| `language` | `VARCHAR(2)` | PK |
| `name` | `VARCHAR(160)` | NOT NULL |
| `country` | `VARCHAR(120)` | NOT NULL |
| `description` | `TEXT` | NOT NULL |

## `experiences`

| Поле | Тип | Ограничения |
|---|---|---|
| `id` | `VARCHAR(36)` | PK |
| `slug` | `VARCHAR(160)` | UNIQUE |
| `vendor_id` | `VARCHAR(36)` | FK → users.id |
| `destination_id` | `VARCHAR(36)` | FK → destinations.id |
| `category` | `VARCHAR(30)` | FK → categories.code |
| `duration_days` | `INTEGER` | NOT NULL |
| `price_from` | `NUMERIC(12, 2)` | NOT NULL |
| `currency` | `VARCHAR(3)` | NOT NULL |
| `rating` | `NUMERIC(2, 1)` | NOT NULL |
| `review_count` | `INTEGER` | NOT NULL |
| `image_url` | `VARCHAR(2000)` | NOT NULL |
| `is_published` | `BOOLEAN` | NOT NULL |
| `is_monitoring` | `BOOLEAN` | NOT NULL, default false; скрыт в обычном каталоге |
| `created_at` | `DATETIME` | NOT NULL |
| `publication_status` | `VARCHAR(20)` | NOT NULL |
| `min_participants` | `INTEGER` | NOT NULL |
| `max_participants` | `INTEGER` | NOT NULL |
| `cancellation_policy_version` | `VARCHAR(30)` | NOT NULL |

CHECK `duration_days >= 1 AND duration_days <= 90`; CHECK `currency = 'KZT'`; CHECK `price_from >= 1`; CHECK `min_participants >= 1 AND max_participants <= 20 AND min_participants <= max_participants`; CHECK `rating >= 0 AND rating <= 5`; UNIQUE `slug`; CHECK `publication_status IN ('draft','published','unpublished','archived') AND is_published = (publication_status = 'published')`.

Индексы: ix_experiences_category (category); ix_experiences_vendor_id (vendor_id); ix_experiences_is_published (is_published); ix_experiences_destination_id (destination_id).

## `password_resets`

| Поле | Тип | Ограничения |
|---|---|---|
| `id` | `VARCHAR(36)` | PK |
| `user_id` | `VARCHAR(36)` | FK → users.id / CASCADE |
| `token_hash` | `VARCHAR(64)` | UNIQUE |
| `credential_digest` | `VARCHAR(64)` | NOT NULL |
| `expires_at` | `DATETIME` | NOT NULL |
| `used_at` | `DATETIME` | NULL |
| `created_at` | `DATETIME` | NOT NULL |

UNIQUE `token_hash`.

Индексы: ix_password_resets_expires_at (expires_at); ix_password_resets_user_id (user_id).

## `revoked_access_tokens`

| Поле | Тип | Ограничения |
|---|---|---|
| `id` | `VARCHAR(36)` | PK |
| `user_id` | `VARCHAR(36)` | FK → users.id / CASCADE |
| `expires_at` | `DATETIME` | NOT NULL |
| `revoked_at` | `DATETIME` | NOT NULL |

Индексы: ix_revoked_access_tokens_expires_at (expires_at); ix_revoked_access_tokens_user_id (user_id).

## `saved_searches`

| Поле | Тип | Ограничения |
|---|---|---|
| `id` | `VARCHAR(36)` | PK |
| `user_id` | `VARCHAR(36)` | FK → users.id / CASCADE |
| `name` | `VARCHAR(120)` | NOT NULL |
| `filters` | `JSON` | NOT NULL |
| `created_at` | `DATETIME` | NOT NULL |

Индексы: ix_saved_searches_user_id (user_id).

## `user_access_boundaries`

| Поле | Тип | Ограничения |
|---|---|---|
| `user_id` | `VARCHAR(36)` | PK, FK → users.id / CASCADE |
| `invalidated_at` | `DATETIME` | NOT NULL |

## `catalog_lines`

| Поле | Тип | Ограничения |
|---|---|---|
| `experience_id` | `VARCHAR(36)` | PK, FK → experiences.id / CASCADE |
| `language` | `VARCHAR(2)` | PK |
| `kind` | `VARCHAR(10)` | PK |
| `position` | `INTEGER` | PK |
| `text` | `VARCHAR(300)` | NOT NULL |

CHECK `kind IN ('tags','included','excluded')`.

## `departures`

| Поле | Тип | Ограничения |
|---|---|---|
| `id` | `VARCHAR(36)` | PK |
| `experience_id` | `VARCHAR(36)` | FK → experiences.id |
| `start_date` | `DATE` | NOT NULL |
| `end_date` | `DATE` | NOT NULL |
| `capacity` | `INTEGER` | NOT NULL |
| `price` | `NUMERIC(12, 2)` | NOT NULL |
| `status` | `VARCHAR(20)` | NOT NULL |

CHECK `price >= 1`; UNIQUE `experience_id, start_date`; CHECK `capacity >= 1 AND capacity <= 1000`; CHECK `end_date >= start_date`; CHECK `status IN ('scheduled','cancelled')`.

Индексы: ix_departures_start_date (start_date); ix_departures_experience_id (experience_id).

## `experience_cancellation_rules`

| Поле | Тип | Ограничения |
|---|---|---|
| `experience_id` | `VARCHAR(36)` | PK, FK → experiences.id / CASCADE |
| `days_before` | `INTEGER` | PK |
| `refund_percent` | `INTEGER` | NOT NULL |

CHECK `days_before BETWEEN 0 AND 3650 AND refund_percent BETWEEN 0 AND 100`.

## `experience_images`

| Поле | Тип | Ограничения |
|---|---|---|
| `id` | `VARCHAR(36)` | PK |
| `experience_id` | `VARCHAR(36)` | FK → experiences.id / CASCADE |
| `position` | `INTEGER` | NOT NULL |
| `url` | `VARCHAR(2000)` | NOT NULL |
| `alt` | `VARCHAR(180)` | NOT NULL |

UNIQUE `experience_id, position`.

Индексы: ix_experience_images_experience_id (experience_id).

## `experience_services`

| Поле | Тип | Ограничения |
|---|---|---|
| `id` | `VARCHAR(36)` | PK |
| `experience_id` | `VARCHAR(36)` | FK → experiences.id / CASCADE |
| `name` | `VARCHAR(180)` | NOT NULL |
| `name_en` | `VARCHAR(180)` | NOT NULL |
| `name_kk` | `VARCHAR(180)` | NOT NULL |
| `price` | `NUMERIC(12, 2)` | NOT NULL |
| `currency` | `VARCHAR(3)` | NOT NULL |
| `per_person` | `BOOLEAN` | NOT NULL |
| `is_active` | `BOOLEAN` | NOT NULL |

CHECK `price >= 0 AND currency = 'KZT'`.

Индексы: ix_experience_services_experience_id (experience_id).

## `experience_translations`

| Поле | Тип | Ограничения |
|---|---|---|
| `experience_id` | `VARCHAR(36)` | PK, FK → experiences.id / CASCADE |
| `language` | `VARCHAR(2)` | PK |
| `title` | `VARCHAR(180)` | NOT NULL |
| `description` | `TEXT` | NOT NULL |

## `favorites`

| Поле | Тип | Ограничения |
|---|---|---|
| `user_id` | `VARCHAR(36)` | PK, FK → users.id / CASCADE |
| `experience_id` | `VARCHAR(36)` | PK, FK → experiences.id / CASCADE |
| `created_at` | `DATETIME` | NOT NULL |

## `itinerary_days`

| Поле | Тип | Ограничения |
|---|---|---|
| `id` | `VARCHAR(36)` | PK |
| `experience_id` | `VARCHAR(36)` | FK → experiences.id / CASCADE |
| `day` | `INTEGER` | NOT NULL |

UNIQUE `experience_id, day`; CHECK `day BETWEEN 1 AND 90`.

Индексы: ix_itinerary_days_experience_id (experience_id).

## `promocodes`

| Поле | Тип | Ограничения |
|---|---|---|
| `id` | `VARCHAR(36)` | PK |
| `code` | `VARCHAR(40)` | UNIQUE |
| `kind` | `VARCHAR(10)` | NOT NULL |
| `value` | `NUMERIC(12, 2)` | NOT NULL |
| `currency` | `VARCHAR(3)` | NOT NULL |
| `min_amount` | `NUMERIC(12, 2)` | NOT NULL |
| `starts_at` | `DATETIME` | NOT NULL |
| `ends_at` | `DATETIME` | NOT NULL |
| `usage_limit` | `INTEGER` | NOT NULL |
| `per_user_limit` | `INTEGER` | NOT NULL |
| `is_active` | `BOOLEAN` | NOT NULL |
| `experience_id` | `VARCHAR(36)` | NULL, FK → experiences.id |
| `category` | `VARCHAR(30)` | NULL, FK → categories.code |

UNIQUE `code`; CHECK `kind IN ('percent','fixed') AND value > 0 AND (kind != 'percent' OR value <= 100) AND min_amount >= 0 AND ends_at > starts_at AND usage_limit > 0 AND per_user_limit > 0 AND currency = 'KZT'`.

## `bookings`

| Поле | Тип | Ограничения |
|---|---|---|
| `id` | `VARCHAR(36)` | PK |
| `reference` | `VARCHAR(20)` | UNIQUE |
| `user_id` | `VARCHAR(36)` | FK → users.id |
| `departure_id` | `VARCHAR(36)` | FK → departures.id |
| `status` | `VARCHAR(20)` | NOT NULL |
| `travelers_count` | `INTEGER` | NOT NULL |
| `total_amount` | `NUMERIC(12, 2)` | NOT NULL |
| `currency` | `VARCHAR(3)` | NOT NULL |
| `contact_name` | `VARCHAR(120)` | NOT NULL |
| `contact_email` | `VARCHAR(254)` | NOT NULL |
| `notes` | `TEXT` | NOT NULL |
| `experience_snapshot` | `JSON` | NOT NULL |
| `start_date` | `DATE` | NOT NULL |
| `end_date` | `DATE` | NOT NULL |
| `created_at` | `DATETIME` | NOT NULL |
| `expires_at` | `DATETIME` | NULL |
| `subtotal_amount` | `NUMERIC(12, 2)` | NOT NULL |
| `discount_amount` | `NUMERIC(12, 2)` | NOT NULL |
| `cancellation_policy` | `JSON` | NOT NULL |

CHECK `total_amount >= 1`; CHECK `travelers_count >= 1 AND travelers_count <= 20`; CHECK `status IN ('pending','confirmed','expired','cancelled','completed')`; CHECK `subtotal_amount >= total_amount AND discount_amount >= 0 AND subtotal_amount - discount_amount = total_amount`; UNIQUE `reference`.

Индексы: ix_bookings_departure_status (departure_id, status); ix_bookings_expires_at (expires_at); ix_bookings_user_id (user_id).

## `itinerary_translations`

| Поле | Тип | Ограничения |
|---|---|---|
| `day_id` | `VARCHAR(36)` | PK, FK → itinerary_days.id / CASCADE |
| `language` | `VARCHAR(2)` | PK |
| `title` | `VARCHAR(180)` | NOT NULL |
| `description` | `TEXT` | NOT NULL |

## `booking_items`

| Поле | Тип | Ограничения |
|---|---|---|
| `id` | `VARCHAR(36)` | PK |
| `booking_id` | `VARCHAR(36)` | FK → bookings.id / CASCADE |
| `service_id` | `VARCHAR(36)` | NULL, FK → experience_services.id |
| `kind` | `VARCHAR(20)` | NOT NULL |
| `name` | `VARCHAR(180)` | NOT NULL |
| `quantity` | `INTEGER` | NOT NULL |
| `unit_amount` | `NUMERIC(12, 2)` | NOT NULL |
| `total_amount` | `NUMERIC(12, 2)` | NOT NULL |
| `currency` | `VARCHAR(3)` | NOT NULL |

CHECK `quantity > 0 AND unit_amount >= 0 AND total_amount >= 0`.

Индексы: ix_booking_items_booking_id (booking_id).

## `booking_participants`

| Поле | Тип | Ограничения |
|---|---|---|
| `id` | `VARCHAR(36)` | PK |
| `booking_id` | `VARCHAR(36)` | FK → bookings.id / CASCADE |
| `position` | `INTEGER` | NOT NULL |
| `name` | `VARCHAR(120)` | NOT NULL |

UNIQUE `booking_id, position`.

Индексы: ix_booking_participants_booking_id (booking_id).

## `booking_status_history`

| Поле | Тип | Ограничения |
|---|---|---|
| `id` | `VARCHAR(36)` | PK |
| `booking_id` | `VARCHAR(36)` | FK → bookings.id |
| `actor_id` | `VARCHAR(36)` | NULL, FK → users.id |
| `reason` | `VARCHAR(500)` | NOT NULL |
| `status` | `VARCHAR(20)` | NOT NULL |
| `created_at` | `DATETIME` | NOT NULL |

Индексы: ix_booking_status_history_booking_id (booking_id).

## `currency_conversion_records`

| Поле | Тип | Ограничения |
|---|---|---|
| `id` | `VARCHAR(36)` | PK |
| `booking_id` | `VARCHAR(36)` | UNIQUE, NULL, FK → bookings.id |
| `experience_id` | `VARCHAR(36)` | UNIQUE, NULL, FK → experiences.id |
| `original_amount` | `NUMERIC(12, 2)` | NOT NULL |
| `original_currency` | `VARCHAR(3)` | NOT NULL |
| `equivalent_amount` | `NUMERIC(12, 2)` | NOT NULL |
| `factor` | `NUMERIC(12, 4)` | NOT NULL |
| `rule` | `VARCHAR(150)` | NOT NULL |
| `created_at` | `DATETIME` | NOT NULL |

UNIQUE `experience_id`; UNIQUE `booking_id`.

## `notifications`

| Поле | Тип | Ограничения |
|---|---|---|
| `id` | `VARCHAR(36)` | PK |
| `user_id` | `VARCHAR(36)` | FK → users.id / CASCADE |
| `event` | `VARCHAR(80)` | NOT NULL |
| `title` | `VARCHAR(200)` | NOT NULL |
| `body` | `TEXT` | NOT NULL |
| `title_en` | `VARCHAR(200)` | NOT NULL |
| `title_kk` | `VARCHAR(200)` | NOT NULL |
| `body_en` | `TEXT` | NOT NULL |
| `body_kk` | `TEXT` | NOT NULL |
| `booking_id` | `VARCHAR(36)` | NULL, FK → bookings.id |
| `is_read` | `BOOLEAN` | NOT NULL |
| `created_at` | `DATETIME` | NOT NULL |

Индексы: ix_notifications_user_read_created (user_id, is_read, created_at).

## `payment_attempts`

| Поле | Тип | Ограничения |
|---|---|---|
| `id` | `VARCHAR(36)` | PK |
| `booking_id` | `VARCHAR(36)` | FK → bookings.id |
| `user_id` | `VARCHAR(36)` | FK → users.id |
| `idempotency_key` | `VARCHAR(100)` | NOT NULL |
| `request_fingerprint` | `VARCHAR(64)` | NOT NULL |
| `provider_operation_id` | `VARCHAR(36)` | UNIQUE, FK → provider_operations.id |
| `instrument_id` | `VARCHAR(40)` | NOT NULL |
| `masked_card` | `VARCHAR(24)` | NOT NULL |
| `status` | `VARCHAR(20)` | NOT NULL |
| `error_code` | `VARCHAR(40)` | NOT NULL |
| `amount` | `NUMERIC(12, 2)` | NOT NULL |
| `currency` | `VARCHAR(3)` | NOT NULL |
| `action_expires_at` | `DATETIME` | NULL |
| `created_at` | `DATETIME` | NOT NULL |

UNIQUE `provider_operation_id`; UNIQUE `user_id, idempotency_key`; CHECK `status IN ('created','requires_action','unknown','succeeded','failed','cancelled') AND amount > 0`.

Индексы: UNIQUE uq_payment_succeeded_booking (booking_id) WHERE status = 'succeeded'; ix_payment_attempts_booking_id (booking_id).

## `promo_redemptions`

| Поле | Тип | Ограничения |
|---|---|---|
| `id` | `VARCHAR(36)` | PK |
| `promo_id` | `VARCHAR(36)` | FK → promocodes.id |
| `booking_id` | `VARCHAR(36)` | UNIQUE, FK → bookings.id |
| `user_id` | `VARCHAR(36)` | FK → users.id |
| `discount_amount` | `NUMERIC(12, 2)` | NOT NULL |
| `created_at` | `DATETIME` | NOT NULL |

UNIQUE `booking_id`.

Индексы: ix_promo_redemptions_user_id (user_id); ix_promo_redemptions_promo_id (promo_id).

## `reviews`

| Поле | Тип | Ограничения |
|---|---|---|
| `id` | `VARCHAR(36)` | PK |
| `booking_id` | `VARCHAR(36)` | UNIQUE, FK → bookings.id |
| `user_id` | `VARCHAR(36)` | FK → users.id |
| `experience_id` | `VARCHAR(36)` | FK → experiences.id |
| `rating` | `INTEGER` | NOT NULL |
| `title` | `VARCHAR(180)` | NOT NULL |
| `text` | `TEXT` | NOT NULL |
| `status` | `VARCHAR(20)` | NOT NULL |
| `moderated_by` | `VARCHAR(36)` | NULL, FK → users.id |
| `moderated_at` | `DATETIME` | NULL |
| `created_at` | `DATETIME` | NOT NULL |

UNIQUE `booking_id`; CHECK `status IN ('pending','approved','rejected')`; CHECK `rating >= 1 AND rating <= 5`.

Индексы: ix_reviews_experience_status (experience_id, status); ix_reviews_user_id (user_id).

## `support_tickets`

| Поле | Тип | Ограничения |
|---|---|---|
| `id` | `VARCHAR(36)` | PK |
| `user_id` | `VARCHAR(36)` | FK → users.id |
| `vendor_id` | `VARCHAR(36)` | NULL, FK → users.id |
| `booking_id` | `VARCHAR(36)` | NULL, FK → bookings.id |
| `subject` | `VARCHAR(180)` | NOT NULL |
| `status` | `VARCHAR(20)` | NOT NULL |
| `created_at` | `DATETIME` | NOT NULL |
| `updated_at` | `DATETIME` | NOT NULL |
| `priority` | `VARCHAR(2)` | NOT NULL, P1/P2/P3 |
| `response_due_at` | `TIMESTAMPTZ` | NULL для неизвестных старых сроков |
| `first_response_at` | `TIMESTAMPTZ` | NULL до содержательной реакции |
| `first_response_by` | `VARCHAR(36)` | NULL, FK → users.id |
| `response_working_seconds` | `INTEGER` | NULL либо ≥ 0 |
| `response_calendar` | `JSON` | NULL либо исторический снимок календаря |

CHECK `status IN ('open','in_progress','resolved','closed')`.

Индексы: ix_support_tickets_user_id (user_id); ix_support_tickets_booking_id (booking_id); ix_support_tickets_vendor_id (vendor_id); ix_support_response_due_priority (response_due_at, priority).

В `bookings` также добавлен `is_synthetic BOOLEAN NOT NULL DEFAULT false`
с индексом `ix_bookings_is_synthetic`. Его задаёт сервер из типа технической
учётной записи; пользователь не может передать этот флаг в оформлении.
В `experiences` добавлен индекс `ix_experiences_is_monitoring`.

## `payment_events`

| Поле | Тип | Ограничения |
|---|---|---|
| `id` | `VARCHAR(36)` | PK |
| `payment_id` | `VARCHAR(36)` | FK → payment_attempts.id |
| `status` | `VARCHAR(20)` | NOT NULL |
| `reason` | `VARCHAR(500)` | NOT NULL |
| `created_at` | `DATETIME` | NOT NULL |

Индексы: ix_payment_events_payment_id (payment_id).

## `refunds`

| Поле | Тип | Ограничения |
|---|---|---|
| `id` | `VARCHAR(36)` | PK |
| `booking_id` | `VARCHAR(36)` | FK → bookings.id |
| `payment_id` | `VARCHAR(36)` | FK → payment_attempts.id |
| `provider_operation_id` | `VARCHAR(36)` | UNIQUE, FK → provider_operations.id |
| `idempotency_key` | `VARCHAR(100)` | UNIQUE |
| `amount` | `NUMERIC(12, 2)` | NOT NULL |
| `currency` | `VARCHAR(3)` | NOT NULL |
| `reason` | `VARCHAR(500)` | NOT NULL |
| `status` | `VARCHAR(20)` | NOT NULL |
| `actor_id` | `VARCHAR(36)` | NULL, FK → users.id |
| `created_at` | `DATETIME` | NOT NULL |

UNIQUE `provider_operation_id`; UNIQUE `idempotency_key`; CHECK `amount > 0 AND status IN ('pending','succeeded','failed')`.

Индексы: ix_refunds_booking_id (booking_id); ix_refunds_payment_id (payment_id).

## `support_messages`

| Поле | Тип | Ограничения |
|---|---|---|
| `id` | `VARCHAR(36)` | PK |
| `ticket_id` | `VARCHAR(36)` | FK → support_tickets.id / CASCADE |
| `author_id` | `VARCHAR(36)` | FK → users.id |
| `author_role` | `VARCHAR(20)` | NOT NULL |
| `body` | `TEXT` | NOT NULL |
| `created_at` | `DATETIME` | NOT NULL |

Индексы: ix_support_messages_ticket_id (ticket_id).

## `refund_events`

| Поле | Тип | Ограничения |
|---|---|---|
| `id` | `VARCHAR(36)` | PK |
| `refund_id` | `VARCHAR(36)` | FK → refunds.id |
| `status` | `VARCHAR(20)` | NOT NULL |
| `reason` | `VARCHAR(500)` | NOT NULL |
| `created_at` | `DATETIME` | NOT NULL |

Индексы: ix_refund_events_refund_id (refund_id).
