# Деплой ПолБаки на VPS

Вся система (база, API, бот, HTTPS) поднимается на сервере одной командой.
Локально сборка уже проверена — образ собирается и работает.

## 0. Что нужно заранее

1. **VPS** с Ubuntu 22.04/24.04, минимум 2 ГБ RAM. Российские хостеры с оплатой картой РФ:
   Timeweb Cloud, Selectel, Beget, Reg.ru (~300–600 ₽/мес).
2. **Домен** (например `polbaka.ru`) — там же или на reg.ru.
3. **Боевой бот** у @BotFather — отдельный от тестового (или переиспользуем тот же токен).

## 1. Домен → сервер (DNS)

В панели домена создай A-запись:

```
@    A    <IP твоего VPS>
www  A    <IP твоего VPS>
```

DNS обновляется от нескольких минут до пары часов. Проверить: `ping polbaka.ru` должен отвечать с IP сервера.

> ⚠️ HTTPS и **геолокация на сайте работают только по домену** — по голому IP браузер геопозицию не даст. Поэтому домен обязателен, а не «на будущее».

## 2. Подготовка сервера

Подключаемся по SSH (`ssh root@<IP>`) и ставим Docker:

```bash
curl -fsSL https://get.docker.com | sh
```

## 3. Заливаем проект

Вариант через git (если выложишь репозиторий) или scp-копированием папки. Нужны файлы:
`Dockerfile`, `docker-compose.prod.yml`, `Caddyfile`, `requirements.txt`, папки `app/`, `bot/`, `web/`, `scripts/`, `db/`.

## 4. Настраиваем секреты

На сервере в папке проекта создай файл `.env` по образцу `.env.prod.example`:

```
POSTGRES_USER=benzradar
POSTGRES_PASSWORD=<длинный случайный пароль>
POSTGRES_DB=benzradar
BOT_TOKEN=<токен боевого бота>
DOMAIN=polbaka.ru
```

## 5. Запуск

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

Поднимутся 4 контейнера: `db`, `api`, `bot`, `caddy`. Caddy сам получит HTTPS-сертификат
(нужно, чтобы DNS из шага 1 уже указывал на сервер).

## 6. Наполняем базу заправками (один раз)

Схема таблиц создаётся автоматически, но заправки нужно импортировать:

```bash
docker compose -f docker-compose.prod.yml run --rm api python scripts/import_stations.py
```

> ❗ **Демо-данные (`seed_demo.py`) на прод НЕ запускаем** — фейковые отметки убьют доверие
> к сервису. На проде отметки появляются только от реальных людей.

## 7. Проверка

- Открой `https://polbaka.ru` — карта с заправками, замок HTTPS в адресной строке.
- Напиши боевому боту `/start`.

## Полезные команды

```bash
docker compose -f docker-compose.prod.yml ps           # статус контейнеров
docker compose -f docker-compose.prod.yml logs -f api  # логи API
docker compose -f docker-compose.prod.yml logs -f bot  # логи бота
docker compose -f docker-compose.prod.yml down         # остановить всё
docker compose -f docker-compose.prod.yml up -d --build # обновить после правок кода
```

## Обновление актуальности заправок

Периодически (раз в неделю-две) можно перезапускать импорт из OSM — он апсертит по osm_id,
дублей не создаёт:

```bash
docker compose -f docker-compose.prod.yml run --rm api python scripts/import_stations.py
```
