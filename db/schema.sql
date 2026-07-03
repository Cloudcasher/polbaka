-- BenzRadar — схема базы данных
-- Выполняется автоматически при первом запуске контейнера Postgres.

-- Гео-расширение: точки на карте, поиск ближайших АЗС в радиусе
CREATE EXTENSION IF NOT EXISTS postgis;

-- ── Перечисления (строгие значения для «умного ядра») ───────────────────────
CREATE TYPE fuel_type     AS ENUM ('AI92', 'AI95', 'AI98', 'AI100', 'DT', 'GAS');
CREATE TYPE report_status AS ENUM ('available', 'low', 'queue', 'empty');
CREATE TYPE report_source AS ENUM ('web', 'bot');

-- ── Заправки (импортируются из OpenStreetMap) ──────────────────────────────
CREATE TABLE stations (
    id          BIGSERIAL PRIMARY KEY,
    osm_id      BIGINT UNIQUE,                 -- id объекта в OSM (защита от дублей при повторном импорте)
    name        TEXT,
    brand       TEXT,                          -- Лукойл, Газпромнефть и т.п.
    lat         DOUBLE PRECISION NOT NULL,
    lon         DOUBLE PRECISION NOT NULL,
    geom        GEOGRAPHY(Point, 4326),        -- та же точка для гео-запросов (метры)
    address     TEXT,
    city        TEXT,
    region      TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- Пространственный индекс: быстрый поиск «что рядом»
CREATE INDEX idx_stations_geom ON stations USING GIST (geom);

-- ── Пользователи (веб-анонимы и залогиненные через Telegram) ───────────────
CREATE TABLE users (
    id            BIGSERIAL PRIMARY KEY,
    tg_id         BIGINT UNIQUE,               -- NULL у анонима
    is_anonymous  BOOLEAN NOT NULL DEFAULT true,
    reputation    REAL    NOT NULL DEFAULT 0.3, -- аноним 0.3; залогиненный стартует с 1.0
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ── Отметки о наличии топлива ──────────────────────────────────────────────
CREATE TABLE reports (
    id           BIGSERIAL PRIMARY KEY,
    station_id   BIGINT NOT NULL REFERENCES stations(id) ON DELETE CASCADE,
    user_id      BIGINT          REFERENCES users(id)    ON DELETE SET NULL,
    fuel_type    fuel_type     NOT NULL,
    status       report_status NOT NULL,
    queue_min    INT,                          -- оценка очереди в минутах (необязательно)
    limit_liters INT,                          -- лимит отпуска в литрах (необязательно)
    comment      TEXT,                         -- необязательный свободный текст поверх шаблона
    source       report_source NOT NULL DEFAULT 'web',
    created_at   TIMESTAMPTZ   NOT NULL DEFAULT now()
);
-- Индекс под главный запрос: «последние отметки по АЗС и марке топлива»
CREATE INDEX idx_reports_station_fuel ON reports (station_id, fuel_type, created_at DESC);

-- ── Подписки бота (уведомить, когда появится топливо) ──────────────────────
CREATE TABLE subscriptions (
    id          BIGSERIAL PRIMARY KEY,
    user_id     BIGINT NOT NULL REFERENCES users(id)    ON DELETE CASCADE,
    station_id  BIGINT NOT NULL REFERENCES stations(id) ON DELETE CASCADE,
    fuel_type   fuel_type NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, station_id, fuel_type)   -- одна подписка на связку
);
-- Сигнал о новой отметке: Postgres LISTEN/NOTIFY.
-- Бот держит соединение с LISTEN new_report и мгновенно узнаёт о каждой
-- вставке в reports — независимо от того, пришла она с сайта или из бота.

CREATE OR REPLACE FUNCTION notify_new_report() RETURNS trigger AS $$
BEGIN
    PERFORM pg_notify('new_report', json_build_object(
        'station_id', NEW.station_id,
        'fuel_type',  NEW.fuel_type,
        'status',     NEW.status
    )::text);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS reports_notify ON reports;
CREATE TRIGGER reports_notify
    AFTER INSERT ON reports
    FOR EACH ROW EXECUTE FUNCTION notify_new_report();
