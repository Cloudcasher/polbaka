// ПолБака — логика карты.
// Данные берём у нашего же API (мы на одном домене, путь относительный).

const FUEL_LABELS = { AI92: "АИ-92", AI95: "АИ-95", AI98: "АИ-98", AI100: "АИ-100", DT: "ДТ", GAS: "Газ" };
const STATUS_LABELS = { available: "✅ Есть", low: "🟡 Мало", queue: "🕐 Очередь", empty: "❌ Пусто" };

// Уровень доверия — текстом, а не только цветом (ядро продукта должно быть видно)
const LEVEL_BADGES = {
    confirmed: '<span class="lvl lvl-ok">✓✓ подтверждено</span>',
    single: '<span class="lvl lvl-mid">1 отметка</span>',
    stale: '<span class="lvl lvl-old">устарело</span>',
};

// Экранирование: названия/адреса приходят из OSM, который правит кто угодно —
// без этого любой вандал может вписать <script> в имя заправки (stored XSS)
function esc(s) {
    return String(s ?? "").replace(/[&<>"']/g, (c) => ({
        "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[c]));
}

// Цвета статусов живут в одном месте — style.css (:root),
// JS читает их оттуда: правишь палитру — меняется и карта, и легенда
const _css = getComputedStyle(document.documentElement);
const COLORS = {
    ok: _css.getPropertyValue("--c-ok").trim(),
    okSoft: _css.getPropertyValue("--c-ok-soft").trim(),
    warn: _css.getPropertyValue("--c-warn").trim(),
    bad: _css.getPropertyValue("--c-bad").trim(),
    na: _css.getPropertyValue("--c-na").trim(),
};

function markerColor(fs) {
    if (!fs || fs.level === "stale") return COLORS.na;
    if (fs.status === "available")
        return fs.level === "confirmed" ? COLORS.ok : COLORS.okSoft;
    if (fs.status === "empty") return COLORS.bad;
    return COLORS.warn; // мало / очередь
}

function formatAge(min) {
    if (min < 1) return "только что";
    if (min < 60) return `${min} мин назад`;
    return `${Math.floor(min / 60)} ч назад`;
}

// Расстояние между двумя точками, км (формула гаверсинусов)
function distanceKm(lat1, lon1, lat2, lon2) {
    const R = 6371, rad = Math.PI / 180;
    const dLat = (lat2 - lat1) * rad, dLon = (lon2 - lon1) * rad;
    const a = Math.sin(dLat / 2) ** 2 +
        Math.cos(lat1 * rad) * Math.cos(lat2 * rad) * Math.sin(dLon / 2) ** 2;
    return R * 2 * Math.asin(Math.sqrt(a));
}

// ── Карта ────────────────────────────────────────────────────────────────
const map = L.map("map").setView([59.94, 30.31], 11); // центр Питера
map.attributionControl.setPrefix(""); // убираем приписку Leaflet из угла карты

// Voyager — живая, но аккуратная подложка: цвета есть,
// а визуального мусора (кресты аптек и т.п.) — нет
L.tileLayer("https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png", {
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/attributions">CARTO</a>',
    maxZoom: 19,
    subdomains: "abcd",
}).addTo(map);

let currentFuel = "AI95";
let currentView = "all";        // all | available | usable
let stationsCache = [];         // последние загруженные станции
let fetchedBounds = null;       // область, для которой данные уже скачаны
// Кластеры: на дальних зумах соседние АЗС схлопываются в кружок с числом —
// карта остаётся читаемой хоть с 937 точками, хоть с 10 000
const markersLayer = L.markerClusterGroup({
    disableClusteringAtZoom: 14,     // на уровне улиц — все пины по отдельности
    maxClusterRadius: 60,
    showCoverageOnHover: false,
    spiderfyOnMaxZoom: true,         // пины в одной точке раскрываются веером
}).addTo(map);

// ── Геопозиция пользователя ──────────────────────────────────────────────
let userPos = null;

navigator.geolocation?.getCurrentPosition(
    (pos) => {
        userPos = [pos.coords.latitude, pos.coords.longitude];
        L.marker(userPos, {
            icon: L.divIcon({ className: "", html: '<div class="user-dot"></div>', iconSize: [18, 18], iconAnchor: [9, 9] }),
            interactive: false,
        }).addTo(map);
        renderMarkers(); // перерисовать попапы уже с расстояниями
    },
    () => {}, // отказ — просто работаем без расстояний
    { enableHighAccuracy: false, timeout: 8000 },
);

// ── Иконки-пины ──────────────────────────────────────────────────────────
function stationIcon(fs) {
    const color = markerColor(fs);
    if (!fs || fs.level === "stale") {
        // «Нет данных» — маленькая тихая точка; контейнер 22px, чтобы
        // в неё можно было попасть пальцем (сама точка 10px — визуально тихая)
        return L.divIcon({
            className: "",
            html: `<div class="dot-marker" style="--c:${color}"></div>`,
            iconSize: [22, 22],
            iconAnchor: [11, 11],
        });
    }
    return L.divIcon({
        className: "",
        html: `<div class="pin" style="--c:${color}"><span>⛽</span></div>`,
        iconSize: [30, 38],
        iconAnchor: [15, 36],
        popupAnchor: [0, -34],
    });
}

// ── Баннер «нет связи» ───────────────────────────────────────────────────
function setOffline(isOffline) {
    document.getElementById("net-banner").hidden = !isOffline;
}

// ── Загрузка станций (с запасом вокруг экрана) ───────────────────────────
async function loadStations(force = false) {
    const view = map.getBounds();
    // Если двигаемся внутри уже скачанной области — не перерисовываем
    // (иначе пересоздание маркеров закрывало открытый попап)
    if (!force && fetchedBounds && fetchedBounds.contains(view)) return;

    const padded = view.pad(0.6); // качаем с запасом 60% вокруг экрана
    const bbox = [padded.getWest(), padded.getSouth(), padded.getEast(), padded.getNorth()].join(",");
    try {
        // Отменяем предыдущий запрос: иначе при быстрой смене фильтров
        // старый ответ мог приехать позже нового и затереть его
        loadController?.abort();
        loadController = new AbortController();
        const resp = await fetch(`/stations?bbox=${bbox}&fuel=${currentFuel}`, {
            signal: loadController.signal,
        });
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        stationsCache = await resp.json();
        fetchedBounds = padded;
        setOffline(false);
        renderMarkers();
    } catch (e) {
        if (e.name === "AbortError") return; // отменили сами — это не ошибка
        // Молчать нельзя: юзер должен знать, что картина могла устареть
        setOffline(true);
    }
}
let loadController = null;

// Автообновление: свежесть — ядро продукта, данные не должны замирать
// на открытой вкладке. Пока открыт попап — не трогаем (закроется при перерисовке).
let popupIsOpen = false;
map.on("popupopen", () => { popupIsOpen = true; });
map.on("popupclose", () => { popupIsOpen = false; });
setInterval(() => {
    if (!popupIsOpen) loadStations(true);
}, 75_000);

// ── Отрисовка маркеров из кэша (с учётом фильтра наличия) ────────────────
let selectedEl = null; // элемент подсвеченного (открытого) пина

function renderMarkers() {
    markersLayer.clearLayers();
    let shown = 0;
    for (const st of stationsCache) {
        const fs = st.fuel_statuses[currentFuel] || null;

        if (currentView === "available" && !(fs && fs.status === "available" && fs.level !== "stale")) continue;
        if (currentView === "usable" && !(fs && fs.status !== "empty" && fs.level !== "stale")) continue;

        const marker = L.marker([st.lat, st.lon], { icon: stationIcon(fs) });
        marker.bindPopup(() => popupHtml(st), { minWidth: 250 });
        marker.on("click", () => {
            map.flyTo([st.lat, st.lon], Math.max(map.getZoom(), 14), { duration: 0.7 });
        });
        // Активная АЗС выделяется: пин крупнее и с тенью
        marker.on("popupopen", () => {
            selectedEl?.classList.remove("selected-marker");
            selectedEl = marker.getElement();
            selectedEl?.classList.add("selected-marker");
        });
        marker.on("popupclose", () => {
            marker.getElement()?.classList.remove("selected-marker");
        });
        marker.addTo(markersLayer);
        shown++;
    }

    // Пустое состояние: молчаливая пустая карта выглядит как поломка
    const hint = document.getElementById("empty-hint");
    if (shown === 0) {
        hint.textContent = stationsCache.length === 0
            ? "В этой области нет заправок — подвинь карту"
            : "Под текущий фильтр ничего не попало — сними фильтр или подвинь карту";
        hint.hidden = false;
    } else {
        hint.hidden = true;
    }

    document.getElementById("loading")?.remove(); // первая загрузка завершена
}

map.on("moveend", () => loadStations());

// ── Карточка АЗС ─────────────────────────────────────────────────────────
function popupHtml(st) {
    const name = st.name || st.brand || "АЗС";
    const div = document.createElement("div");
    div.className = "popup-card";

    const dist = userPos
        ? `<span class="dist">📍 ${distanceKm(userPos[0], userPos[1], st.lat, st.lon).toFixed(1)} км по прямой</span>`
        : "";

    let statusRows = "";
    const fuels = Object.keys(st.fuel_statuses);
    if (fuels.length === 0) {
        statusRows = '<div class="fuel-row meta">Отметок пока нет — будь первым!</div>';
    } else {
        for (const fuel of fuels.sort()) {
            const fs = st.fuel_statuses[fuel];
            const extras = [];
            if (fs.queue_min) extras.push(`очередь ~${fs.queue_min} мин`);
            if (fs.limit_liters) extras.push(`лимит ${fs.limit_liters} л`);
            extras.push(formatAge(fs.age_min));
            statusRows += `<div class="fuel-row">${FUEL_LABELS[fuel]}: ${STATUS_LABELS[fs.status]} ${LEVEL_BADGES[fs.level]}
                <span class="meta">· ${extras.join(" · ")}</span></div>`;
        }
    }

    div.innerHTML = `
        <h3>${esc(name)}</h3>
        <div class="addr">${esc(st.address || "")} ${dist}</div>
        ${statusRows}
        <div class="report-form">
            <p>Что с <b>${FUEL_LABELS[currentFuel]}</b> прямо сейчас?</p>
            <div class="status-buttons">
                ${Object.entries(STATUS_LABELS).map(([code, label]) =>
                    `<button data-status="${code}">${label}</button>`).join("")}
            </div>
            <div class="report-details" hidden>
                <div class="preset-row" data-kind="queue">
                    <span>Очередь:</span>
                    <button data-val="" class="selected">нет</button>
                    <button data-val="10">~10</button>
                    <button data-val="30">~30</button>
                    <button data-val="60">60+ мин</button>
                </div>
                <div class="preset-row" data-kind="limit">
                    <span>Лимит:</span>
                    <button data-val="" class="selected">нет</button>
                    <button data-val="10">10</button>
                    <button data-val="20">20</button>
                    <button data-val="30">30 л</button>
                </div>
                <button class="send-btn">Отправить</button>
            </div>
        </div>`;

    // Состояние формы: статус обязателен, очередь/лимит — опциональные уточнения
    let selStatus = null, selQueue = "", selLimit = "";
    const details = div.querySelector(".report-details");

    async function send() {
        let errMsg = "Не получилось отправить — проверь связь и попробуй ещё раз";
        try {
            const body = { station_id: st.id, fuel_type: currentFuel, status: selStatus };
            if (selQueue) body.queue_min = Number(selQueue);
            if (selLimit) body.limit_liters = Number(selLimit);
            const resp = await fetch("/reports", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(body),
            });
            if (resp.status === 429) errMsg = "Слишком много отметок подряд — передохни немного 😉";
            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
            div.querySelector(".report-form").innerHTML =
                '<div class="report-thanks">Спасибо! Отметка учтена 🙌</div>';
            loadStations(true);
        } catch {
            // Ошибка НЕ съедает форму: всё остаётся на месте, можно повторить
            let err = div.querySelector(".report-error");
            if (!err) {
                err = document.createElement("div");
                err.className = "report-error";
                div.querySelector(".report-form").appendChild(err);
            }
            err.textContent = errMsg;
        }
    }

    div.querySelectorAll(".status-buttons button").forEach((btn) => {
        btn.addEventListener("click", () => {
            selStatus = btn.dataset.status;
            div.querySelectorAll(".status-buttons button")
                .forEach((b) => b.classList.toggle("selected", b === btn));
            if (selStatus === "empty") {  // «пусто»: очередь/лимит не имеют смысла
                send();
                return;
            }
            details.hidden = false;
        });
    });

    div.querySelectorAll(".preset-row button").forEach((btn) => {
        btn.addEventListener("click", () => {
            const row = btn.closest(".preset-row");
            row.querySelectorAll("button").forEach((b) => b.classList.toggle("selected", b === btn));
            if (row.dataset.kind === "queue") selQueue = btn.dataset.val;
            else selLimit = btn.dataset.val;
        });
    });

    div.querySelector(".send-btn").addEventListener("click", send);

    return div;
}

// ── Фильтры ──────────────────────────────────────────────────────────────
document.querySelectorAll("#fuel-filter button").forEach((btn) => {
    btn.addEventListener("click", () => {
        document.querySelector("#fuel-filter .active").classList.remove("active");
        btn.classList.add("active");
        currentFuel = btn.dataset.fuel;
        document.getElementById("legend-fuel").textContent = FUEL_LABELS[currentFuel];
        loadStations(true);
    });
});

document.querySelectorAll("#view-filter button").forEach((btn) => {
    btn.addEventListener("click", () => {
        document.querySelector("#view-filter .active").classList.remove("active");
        btn.classList.add("active");
        currentView = btn.dataset.view;
        renderMarkers(); // данные уже есть — просто фильтруем на месте
    });
});

// На телефоне легенда по умолчанию свёрнута — экономим экран
if (window.matchMedia("(max-width: 640px)").matches) {
    document.getElementById("legend").open = false;
}

loadStations(true);
