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
