// Admin Panel Controller

let adminToken = localStorage.getItem("sb_admin_token");
let currentTab = "dashboard";

let overviewMap = null;
let overviewMarkers = [];
let overviewSchoolMarker = null;

let stopPickerMap = null;
let stopPickerMarker = null;
let pickerStopMarkers = [];
let pickerSchoolMarker = null;
let lastAddedStopCoord = null;

const FERGANA_CENTER = [40.386400, 71.786400];
const SCHOOL_COORDS = [40.386400, 71.786400];

document.addEventListener("DOMContentLoaded", () => {
  if (adminToken) {
    checkAdminAuth();
  } else {
    showAdminLogin();
  }
});

function showToast(message, type = "info") {
  const container = document.getElementById("toastContainer");
  const el = document.createElement("div");
  el.className = `toast toast-${type}`;
  let icon = "ℹ️";
  if (type === "success") icon = "✅";
  if (type === "error") icon = "❌";
  el.innerHTML = `<span>${icon}</span> <span>${message}</span>`;
  container.appendChild(el);
  setTimeout(() => el.remove(), 4000);
}

function showAdminLogin() {
  document.getElementById("adminLoginSection").style.display = "block";
  document.getElementById("adminAppLayout").style.display = "none";
}

function showAdminApp() {
  document.getElementById("adminLoginSection").style.display = "none";
  document.getElementById("adminAppLayout").style.display = "grid";
}

async function handleAdminLogin(e) {
  e.preventDefault();
  const username = document.getElementById("adminLoginUsername").value.trim();
  const password = document.getElementById("adminLoginPassword").value;

  try {
    const res = await fetch("/api/admin/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password })
    });
    const data = await res.json();
    if (!res.ok) {
      showToast(data.detail || "Kirishda xatolik yuz berdi", "error");
      return;
    }

    adminToken = data.token;
    localStorage.setItem("sb_admin_token", adminToken);
    localStorage.setItem("sb_admin_user", JSON.stringify(data.user));

    showToast("Admin paneliga muvaffaqiyatli kirildi", "success");
    showAdminApp();
    initAdminData();
  } catch (err) {
    showToast("Server bilan aloqa uzildi", "error");
  }
}

function adminLogout() {
  localStorage.removeItem("sb_admin_token");
  localStorage.removeItem("sb_admin_user");
  adminToken = null;
  showAdminLogin();
}

function checkAdminAuth() {
  const userStr = localStorage.getItem("sb_admin_user");
  if (userStr) {
    try {
      const user = JSON.parse(userStr);
      document.getElementById("adminCurrentUserName").textContent = user.full_name || user.username;
    } catch (e) {}
  }
  showAdminApp();
  initAdminData();
}

function initAdminData() {
  loadDashboardStats();
  // Auto refresh stats every 8 seconds
  setInterval(() => {
    if (adminToken && currentTab === "dashboard") {
      loadDashboardStats(false);
    }
  }, 8000);
}

// TAB SWITCHING
function switchTab(tabId) {
  currentTab = tabId;

  // Sidebar item styling
  document.querySelectorAll(".sidebar-menu .menu-item").forEach(el => el.classList.remove("active"));
  event.currentTarget.classList.add("active");

  // View panels
  document.querySelectorAll(".admin-view-panel").forEach(el => el.classList.remove("active"));
  const target = document.getElementById(`view-${tabId}`);
  if (target) target.classList.add("active");

  // Titles
  const titles = {
    "dashboard": ["Bosh Sahifa", "Barcha avtobuslar va safarlarning umumiy statistikasi"],
    "live-map": ["Jonli Xarita", "Barcha 11 ta yo‘nalish va avtobuslarning jonli monitoringi"],
    "buses": ["Avtobuslarni Boshqarish", "Avtobuslarni qo‘shish, tahrirlash, biriktirish va o‘chirish"],
    "routes": ["Yo‘nalishlarni Boshqarish", "10-11 ta maktab yo‘nalishlari va ularga biriktirilgan transportlar"],
    "stops": ["Bekatlarni Boshqarish", "Xaritadan nuqta tanlash orqali bekatlarni kiritish va tahrirlash"],
    "drivers": ["Haydovchilar & Parollar", "Haydovchilar hisoblari, rollar va xavfsiz bcrypt parollar"],
    "telegram": ["Telegram Sozlamalari", "Bot tokeni, guruh chat IDlari va bildirishnomalar jurnali"],
    "trips": ["Safarlar Tarixi", "Barcha bajarilgan va davom etayotgan qatnovlar tarixi"],
    "audit": ["Audit Jurnali", "Administrator va tizim amallarining to‘liq xavfsizlik qaydnomasi"]
  };

  if (titles[tabId]) {
    document.getElementById("pageHeading").textContent = titles[tabId][0];
    document.getElementById("pageSubHeading").textContent = titles[tabId][1];
  }

  // Specific triggers
  if (tabId === "dashboard") loadDashboardStats();
  if (tabId === "live-map") initAdminOverviewMap();
  if (tabId === "buses") loadBuses();
  if (tabId === "routes") loadRoutes();
  if (tabId === "stops") { loadStops(); initStopPickerMap(); }
  if (tabId === "drivers") loadDrivers();
  if (tabId === "telegram") { loadTelegramSettings(); loadTelegramLogs(); }
  if (tabId === "trips") loadTrips();
  if (tabId === "audit") loadAuditLogs();
}

// 1. DASHBOARD STATS
async function loadDashboardStats(showError = true) {
  try {
    const res = await fetch("/api/admin/stats", {
      headers: { "Authorization": `Bearer ${adminToken}` }
    });
    if (!res.ok) {
      if (res.status === 401) { adminLogout(); return; }
      return;
    }
    const data = await res.json();

    document.getElementById("statBuses").textContent = data.total_buses;
    document.getElementById("statRoutes").textContent = data.total_routes;
    document.getElementById("statStops").textContent = data.total_stops;
    document.getElementById("statActiveTrips").textContent = data.active_trips_count;
    document.getElementById("statGpsActive").textContent = data.gps_connected_count;
    document.getElementById("statGpsStale").textContent = data.gps_disconnected_count;
    document.getElementById("statTodayTrips").textContent = data.today_trips_count;
    document.getElementById("statTelegram").textContent = `${data.telegram_sent} / ${data.telegram_failed}`;

    renderDashboardBusesTable(data.buses || []);
  } catch (err) {
    if (showError) console.error("Stats error:", err);
  }
}

function renderDashboardBusesTable(buses) {
  const tbody = document.getElementById("dashboardBusesTableBody");
  if (!buses || buses.length === 0) {
    tbody.innerHTML = '<tr><td colspan="7" style="text-align:center; padding:1.5rem; color:var(--text-muted);">Avtobuslar mavjud emas</td></tr>';
    return;
  }

  tbody.innerHTML = buses.map(b => {
    let gpsBadge = '<span class="badge badge-gray">Kutish rejimida</span>';
    if (b.gps_status === 'active') {
      gpsBadge = '<span class="badge badge-success"><span class="pulse-dot"></span> Aloqa a\'lo</span>';
    } else if (b.gps_status === 'stale') {
      gpsBadge = '<span class="badge badge-danger">⚠️ Aloqa uzilgan</span>';
    }

    const tripBadge = b.trip_id
      ? '<span class="badge badge-warning">Safarda</span>'
      : '<span class="badge badge-gray">To‘xtagan</span>';

    const lastTime = b.last_gps_time 
      ? new Date(b.last_gps_time).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
      : '—';

    return `
      <tr>
        <td style="font-weight:700;">🚌 ${b.bus_name}</td>
        <td><code>${b.plate_number}</code></td>
        <td>${b.route_name ? `${b.route_number}: ${b.route_name}` : '<span style="color:var(--text-dim);">Biriktirilmagan</span>'}</td>
        <td>${b.driver_name || '<span style="color:var(--text-dim);">Biriktirilmagan</span>'}</td>
        <td>${tripBadge}</td>
        <td>${gpsBadge}</td>
        <td>${lastTime}</td>
      </tr>
    `;
  }).join('');
}

// 2. LIVE OVERVIEW MAP
function initAdminOverviewMap() {
  if (!overviewMap) {
    const osmLayer = L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: '&copy; OpenStreetMap contributors',
      maxZoom: 19
    });

    const satelliteLayer = L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", {
      attribution: 'Tiles &copy; Esri',
      maxZoom: 19
    });

    const esriStreets = L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}", {
      attribution: 'Tiles &copy; Esri',
      maxZoom: 19
    });

    overviewMap = L.map("adminOverviewMap", {
      center: FERGANA_CENTER,
      zoom: 13,
      layers: [osmLayer]
    });

    const baseMaps = {
      "🌐 Haqiqiy Xarita (OSM)": osmLayer,
      "🛰️ Sun‘iy Yo‘ldosh (Satellite)": satelliteLayer,
      "🗺️ Esri Ko‘cha Xaritasi": esriStreets
    };
    L.control.layers(baseMaps, null, { position: 'topright' }).addTo(overviewMap);

    // School Marker
    const schoolIcon = L.divIcon({
      className: "school-marker-icon",
      html: `<span>🏫</span>`,
      iconSize: [36, 36],
      iconAnchor: [18, 18]
    });

    overviewSchoolMarker = L.marker(SCHOOL_COORDS, { icon: schoolIcon })
      .bindPopup(`<b>🏫 Farg‘ona Bosh Maktabi (№1)</b><br>Barcha avtobuslar markazi`)
      .addTo(overviewMap);
  }

  loadLiveMapData();
}

async function loadLiveMapData() {
  try {
    const res = await fetch("/api/public/routes");
    const data = await res.json();
    const routes = data.routes || [];

    // Clear existing markers
    overviewMarkers.forEach(m => overviewMap.removeLayer(m));
    overviewMarkers = [];

    routes.forEach(r => {
      if (r.latest_gps && r.latest_gps.latitude && r.latest_gps.longitude) {
        const pos = [r.latest_gps.latitude, r.latest_gps.longitude];
        const icon = L.divIcon({
          className: "bus-marker-icon",
          html: `<span>🚌</span>`,
          iconSize: [36, 36],
          iconAnchor: [18, 18]
        });

        const m = L.marker(pos, { icon })
          .bindPopup(`
            <b>${r.route_number}: ${r.name}</b><br>
            Avtobus: ${r.bus_name} (${r.plate_number})<br>
            Tezlik: ${Math.round(r.latest_gps.speed || 0)} km/s<br>
            Navbatdagi bekat: ${r.next_stop_name || 'Aniqlanmoqda'}
          `)
          .addTo(overviewMap);

        overviewMarkers.push(m);
      }
    });

    if (overviewMarkers.length > 0) {
      const group = new L.featureGroup(overviewMarkers);
      overviewMap.fitBounds(group.getBounds(), { padding: [50, 50] });
    }
  } catch (err) {
    console.error("Map load error:", err);
  }
}

// 3. BUSES CRUD
async function loadBuses() {
  try {
    const res = await fetch("/api/admin/buses", {
      headers: { "Authorization": `Bearer ${adminToken}` }
    });
    const data = await res.json();
    const buses = data.buses || [];
    const tbody = document.getElementById("busesTableBody");

    tbody.innerHTML = buses.map(b => `
      <tr>
        <td>#${b.id}</td>
        <td style="font-weight:700;">${b.bus_name}</td>
        <td><code>${b.plate_number}</code></td>
        <td>${b.model || 'Isuzu'}</td>
        <td>${b.capacity} o‘rin</td>
        <td>${b.route_name ? `${b.route_number}: ${b.route_name}` : '—'}</td>
        <td>${b.is_active ? '<span class="badge badge-success">Faol</span>' : '<span class="badge badge-danger">Nofaol</span>'}</td>
        <td>
          <button class="btn btn-secondary btn-sm" onclick="editBus(${JSON.stringify(b).replace(/"/g, '&quot;')})">Tahrirlash</button>
          <button class="btn btn-danger btn-sm" onclick="deleteBus(${b.id})">O‘chirish</button>
        </td>
      </tr>
    `).join('');
  } catch (err) {
    showToast("Avtobuslarni yuklashda xatolik", "error");
  }
}

function openBusModal(bus = null) {
  document.getElementById("busFormId").value = bus ? bus.id : "";
  document.getElementById("busModalTitle").textContent = bus ? "Avtobusni Tahrirlash" : "Yangi Avtobus";
  document.getElementById("busNameInput").value = bus ? bus.bus_name : "";
  document.getElementById("busPlateInput").value = bus ? bus.plate_number : "";
  document.getElementById("busModelInput").value = bus ? bus.model : "Isuzu SAZ NP 37";
  document.getElementById("busCapacityInput").value = bus ? bus.capacity : "32";
  document.getElementById("busModal").classList.add("active");
}

function editBus(b) {
  openBusModal(b);
}

async function handleBusSubmit(e) {
  e.preventDefault();
  const id = document.getElementById("busFormId").value;
  const bus_name = document.getElementById("busNameInput").value.trim();
  const plate_number = document.getElementById("busPlateInput").value.trim();
  const model = document.getElementById("busModelInput").value.trim();
  const capacity = parseInt(document.getElementById("busCapacityInput").value) || 30;

  try {
    const url = id ? `/api/admin/buses/${id}` : "/api/admin/buses";
    const method = id ? "PUT" : "POST";

    const res = await fetch(url, {
      method,
      headers: {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${adminToken}`
      },
      body: JSON.stringify({ bus_name, plate_number, model, capacity })
    });
    const data = await res.json();
    if (!res.ok) {
      showToast(data.detail || "Xatolik yuz berdi", "error");
      return;
    }

    showToast("Avtobus muvaffaqiyatli saqlandi", "success");
    closeModal("busModal");
    loadBuses();
  } catch (err) {
    showToast("Server bilan aloqa uzildi", "error");
  }
}

async function deleteBus(id) {
  if (!confirm("Haqiqatan ham ushbu avtobusni o‘chirmoqchimisiz? Tarixiy ma’lumotlar saqlab qolinadi.")) return;

  try {
    const res = await fetch(`/api/admin/buses/${id}`, {
      method: "DELETE",
      headers: { "Authorization": `Bearer ${adminToken}` }
    });
    if (res.ok) {
      showToast("Avtobus tizimdan o‘chirildi", "success");
      loadBuses();
    }
  } catch (err) {
    showToast("O‘chirishda xatolik", "error");
  }
}

// 4. ROUTES CRUD
async function loadRoutes() {
  try {
    const res = await fetch("/api/admin/routes", {
      headers: { "Authorization": `Bearer ${adminToken}` }
    });
    const data = await res.json();
    const routes = data.routes || [];
    const tbody = document.getElementById("routesTableBody");

    tbody.innerHTML = routes.map(r => `
      <tr>
        <td><b>${r.route_number}</b></td>
        <td style="font-weight:700;">${r.name}</td>
        <td>${r.bus_name ? `🚌 ${r.bus_name} (${r.plate_number})` : '<span style="color:var(--text-dim);">Biriktirilmagan</span>'}</td>
        <td>${r.driver_name ? `👤 ${r.driver_name}` : '<span style="color:var(--text-dim);">Biriktirilmagan</span>'}</td>
        <td><span class="badge badge-info">${r.stops_count} bekat</span></td>
        <td><code>${r.telegram_chat_id || 'Standart'}</code></td>
        <td>${r.is_active ? '<span class="badge badge-success">Faol</span>' : '<span class="badge badge-danger">To‘xtatilgan</span>'}</td>
        <td>
          <button class="btn btn-secondary btn-sm" onclick="editRoute(${JSON.stringify(r).replace(/"/g, '&quot;')})">Tahrirlash</button>
          <button class="btn btn-danger btn-sm" onclick="deleteRoute(${r.id})">O‘chirish</button>
        </td>
      </tr>
    `).join('');
  } catch (err) {
    showToast("Yo'nalishlarni yuklashda xatolik", "error");
  }
}

async function openRouteModal(route = null) {
  // Populate buses and drivers select options
  const [busesRes, driversRes] = await Promise.all([
    fetch("/api/admin/buses", { headers: { "Authorization": `Bearer ${adminToken}` } }),
    fetch("/api/admin/drivers", { headers: { "Authorization": `Bearer ${adminToken}` } })
  ]);
  const busesData = await busesRes.json();
  const driversData = await driversRes.json();

  const busSelect = document.getElementById("routeBusSelect");
  busSelect.innerHTML = '<option value="0">Avtobus tanlanmagan</option>' +
    (busesData.buses || []).map(b => `<option value="${b.id}">${b.bus_name} (${b.plate_number})</option>`).join('');

  const driverSelect = document.getElementById("routeDriverSelect");
  driverSelect.innerHTML = '<option value="0">Haydovchi tanlanmagan</option>' +
    (driversData.drivers || []).map(d => `<option value="${d.id}">${d.full_name} (${d.username})</option>`).join('');

  document.getElementById("routeFormId").value = route ? route.id : "";
  document.getElementById("routeModalTitle").textContent = route ? "Yo‘nalishni Tahrirlash" : "Yangi Yo‘nalish";
  document.getElementById("routeNumberInput").value = route ? route.route_number : "";
  document.getElementById("routeNameInput").value = route ? route.name : "";
  document.getElementById("routeDescInput").value = route ? (route.description || "") : "";
  document.getElementById("routeTgChatInput").value = route ? (route.telegram_chat_id || "") : "";

  if (route && route.bus_id) busSelect.value = route.bus_id;
  if (route && route.driver_id) driverSelect.value = route.driver_id;

  document.getElementById("routeModal").classList.add("active");
}

function editRoute(r) {
  openRouteModal(r);
}

async function handleRouteSubmit(e) {
  e.preventDefault();
  const id = document.getElementById("routeFormId").value;
  const route_number = document.getElementById("routeNumberInput").value.trim();
  const name = document.getElementById("routeNameInput").value.trim();
  const description = document.getElementById("routeDescInput").value.trim();
  const bus_id = parseInt(document.getElementById("routeBusSelect").value) || null;
  const driver_id = parseInt(document.getElementById("routeDriverSelect").value) || null;
  const telegram_chat_id = document.getElementById("routeTgChatInput").value.trim();

  try {
    const url = id ? `/api/admin/routes/${id}` : "/api/admin/routes";
    const method = id ? "PUT" : "POST";

    const res = await fetch(url, {
      method,
      headers: {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${adminToken}`
      },
      body: JSON.stringify({ route_number, name, description, bus_id, driver_id, telegram_chat_id })
    });
    const data = await res.json();
    if (!res.ok) {
      showToast(data.detail || "Xatolik yuz berdi", "error");
      return;
    }

    showToast("Yo‘nalish saqlandi", "success");
    closeModal("routeModal");
    loadRoutes();
  } catch (err) {
    showToast("Server bilan aloqa uzildi", "error");
  }
}

async function deleteRoute(id) {
  if (!confirm("Haqiqatan ham ushbu yo‘nalishni o‘chirmoqchimisiz?")) return;
  try {
    const res = await fetch(`/api/admin/routes/${id}`, {
      method: "DELETE",
      headers: { "Authorization": `Bearer ${adminToken}` }
    });
    if (res.ok) {
      showToast("Yo‘nalish o‘chirildi", "success");
      loadRoutes();
    }
  } catch (err) {
    showToast("Xatolik", "error");
  }
}

let searchDebounceTimer = null;

// Search places on online map via geocoding
function handleMapSearch(query) {
  clearTimeout(searchDebounceTimer);
  const container = document.getElementById("mapSearchResults");
  if (!query || query.length < 2) {
    container.style.display = "none";
    return;
  }

  searchDebounceTimer = setTimeout(async () => {
    try {
      const res = await fetch(`/api/public/geocode/search?q=${encodeURIComponent(query)}`);
      const data = await res.json();
      const results = data.results || [];

      if (results.length === 0) {
        container.innerHTML = '<div style="color:var(--text-muted); padding:0.5rem; font-size:0.85rem;">Xaritadan joy topilmadi</div>';
        container.style.display = "block";
        return;
      }

      container.innerHTML = results.map(item => `
        <div style="padding:0.6rem; border-bottom:1px solid rgba(255,255,255,0.05); cursor:pointer; font-size:0.88rem;" 
             onclick="selectOnlineSearchResult(${item.lat}, ${item.lon}, '${item.display_name.replace(/'/g, "\\'")}', false)">
          <div style="font-weight:700; color:#38bdf8;">📍 ${item.name || item.display_name.split(',')[0]}</div>
          <div style="font-size:0.75rem; color:var(--text-muted);">${item.display_name}</div>
        </div>
      `).join('');
      container.style.display = "block";
    } catch (err) {
      console.error(err);
    }
  }, 350);
}

function handleModalMapSearch(query) {
  clearTimeout(searchDebounceTimer);
  const container = document.getElementById("modalMapSearchResults");
  if (!query || query.length < 2) {
    container.style.display = "none";
    return;
  }

  searchDebounceTimer = setTimeout(async () => {
    try {
      const res = await fetch(`/api/public/geocode/search?q=${encodeURIComponent(query)}`);
      const data = await res.json();
      const results = data.results || [];

      if (results.length === 0) {
        container.innerHTML = '<div style="color:var(--text-muted); padding:0.5rem; font-size:0.85rem;">Topilmadi</div>';
        container.style.display = "block";
        return;
      }

      container.innerHTML = results.map(item => `
        <div style="padding:0.6rem; border-bottom:1px solid rgba(255,255,255,0.05); cursor:pointer; font-size:0.88rem;" 
             onclick="selectOnlineSearchResult(${item.lat}, ${item.lon}, '${item.display_name.replace(/'/g, "\\'")}', true)">
          <div style="font-weight:700; color:#38bdf8;">📍 ${item.name || item.display_name.split(',')[0]}</div>
          <div style="font-size:0.75rem; color:var(--text-muted);">${item.display_name}</div>
        </div>
      `).join('');
      container.style.display = "block";
    } catch (err) {
      console.error(err);
    }
  }, 350);
}

function selectOnlineSearchResult(lat, lon, fullName, fromModal = false) {
  const cleanName = fullName.split(',')[0].trim();
  document.getElementById("mapSearchResults").style.display = "none";
  document.getElementById("modalMapSearchResults").style.display = "none";

  if (!fromModal) {
    openStopModal();
  }

  document.getElementById("stopNameInput").value = cleanName;
  document.getElementById("stopLatInput").value = parseFloat(lat).toFixed(6);
  document.getElementById("stopLonInput").value = parseFloat(lon).toFixed(6);

  if (stopPickerMap) {
    stopPickerMap.flyTo([lat, lon], 16);
    if (!stopPickerMarker) {
      stopPickerMarker = L.marker([lat, lon], { draggable: true }).addTo(stopPickerMap);
    } else {
      stopPickerMarker.setLatLng([lat, lon]);
    }
  }

  showToast(`Onlayn xaritadan topildi: "${cleanName}"`, "success");
}

// 5. STOPS MANAGEMENT & MAP PICKER
function initStopPickerMap() {
  if (!stopPickerMap) {
    const osmLayer = L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: '&copy; OpenStreetMap contributors',
      maxZoom: 19
    });

    const satelliteLayer = L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", {
      attribution: 'Tiles &copy; Esri',
      maxZoom: 19
    });

    const esriStreets = L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}", {
      attribution: 'Tiles &copy; Esri',
      maxZoom: 19
    });

    stopPickerMap = L.map("stopPickerMap", {
      center: FERGANA_CENTER,
      zoom: 14,
      layers: [osmLayer]
    });

    const baseMaps = {
      "🌐 Haqiqiy Xarita (OSM)": osmLayer,
      "🛰️ Sun‘iy Yo‘ldosh (Satellite)": satelliteLayer,
      "🗺️ Esri Ko‘cha Xaritasi": esriStreets
    };
    L.control.layers(baseMaps, null, { position: 'topright' }).addTo(stopPickerMap);

    // School Marker
    const schoolIcon = L.divIcon({
      className: "school-marker-icon",
      html: `<span>🏫</span>`,
      iconSize: [36, 36],
      iconAnchor: [18, 18]
    });

    pickerSchoolMarker = L.marker(SCHOOL_COORDS, { icon: schoolIcon })
      .bindPopup(`
        <div style="font-family:inherit;">
          <b style="color:#ef4444; font-size:1.05rem;">🏫 Farg‘ona Bosh Maktabi (№1)</b><br>
          <span style="font-size:0.85rem; color:#475569;">Al-Farg‘oniy / Sayilgoh ko‘chasi, Farg‘ona</span><br>
          <span style="font-size:0.8rem; color:#10b981; font-weight:600;">Maktab barcha yo‘nalishlar markazi</span>
        </div>
      `)
      .addTo(stopPickerMap);

    stopPickerMap.on("click", async (e) => {
      const { lat, lng } = e.latlng;
      if (!stopPickerMarker) {
        const pickerIcon = L.divIcon({
          className: "stop-marker-icon next",
          html: `<span>📍</span>`,
          iconSize: [32, 32],
          iconAnchor: [16, 16]
        });
        stopPickerMarker = L.marker([lat, lng], { draggable: true, icon: pickerIcon }).addTo(stopPickerMap);
        stopPickerMarker.on("dragend", async (ev) => {
          const pos = ev.target.getLatLng();
          await applyReverseGeocodeToModal(pos.lat, pos.lng);
        });
      } else {
        stopPickerMarker.setLatLng([lat, lng]);
      }
      await applyReverseGeocodeToModal(lat, lng);
    });
  }

  // Ensure map tiles redraw cleanly if tab was hidden
  setTimeout(() => {
    if (stopPickerMap) stopPickerMap.invalidateSize();
  }, 250);
}

function renderStopsOnPickerMap(stops) {
  if (!stopPickerMap) return;

  // Clear existing stop markers on picker map
  pickerStopMarkers.forEach(layer => stopPickerMap.removeLayer(layer));
  pickerStopMarkers = [];

  stops.forEach((s, idx) => {
    // Stop pin marker
    const stopIcon = L.divIcon({
      className: "stop-marker-icon",
      html: `<span>${idx + 1}</span>`,
      iconSize: [26, 26],
      iconAnchor: [13, 13]
    });

    const marker = L.marker([s.latitude, s.longitude], { icon: stopIcon })
      .bindPopup(`
        <div style="font-family:inherit; min-width:180px;">
          <b style="color:#0284c7; font-size:1rem;">📍 ${s.name}</b><br>
          <span style="font-size:0.8rem; color:#64748b;">ID: #${s.id} | Radiusi: ${s.default_geofence_radius}m</span><br>
          <span style="font-size:0.8rem; color:#10b981;">Yo‘nalishlarda: ${s.routes_count} ta</span><br>
          <div style="margin-top:8px;">
            <button class="btn btn-primary btn-sm" style="padding:2px 8px; font-size:0.75rem;" onclick="editStop(${JSON.stringify(s).replace(/"/g, '&quot;')})">Tahrirlash</button>
          </div>
        </div>
      `)
      .addTo(stopPickerMap);

    // Geofence radius circle
    const circle = L.circle([s.latitude, s.longitude], {
      radius: s.default_geofence_radius || 100,
      color: "#38bdf8",
      weight: 1.5,
      opacity: 0.6,
      fillColor: "#38bdf8",
      fillOpacity: 0.08
    }).addTo(stopPickerMap);

    pickerStopMarkers.push(marker);
    pickerStopMarkers.push(circle);
  });
}

async function applyReverseGeocodeToModal(lat, lon) {
  openStopModal();
  document.getElementById("stopLatInput").value = lat.toFixed(6);
  document.getElementById("stopLonInput").value = lon.toFixed(6);

  try {
    const res = await fetch(`/api/public/geocode/reverse?lat=${lat}&lon=${lon}`);
    const data = await res.json();
    if (data.name) {
      document.getElementById("stopNameInput").value = data.name;
    }
  } catch (err) {
    // If reverse geocoding is slow or fails, fallback to coordinates
  }
}

async function loadStops() {
  try {
    const res = await fetch("/api/admin/stops", {
      headers: { "Authorization": `Bearer ${adminToken}` }
    });
    const data = await res.json();
    const stops = data.stops || [];
    const tbody = document.getElementById("stopsTableBody");

    tbody.innerHTML = stops.map(s => `
      <tr>
        <td>#${s.id}</td>
        <td style="font-weight:700;">📍 ${s.name}</td>
        <td><code>${s.latitude.toFixed(5)}</code></td>
        <td><code>${s.longitude.toFixed(5)}</code></td>
        <td>${s.default_geofence_radius} metr</td>
        <td><span class="badge badge-info">${s.routes_count} yo‘nalishda</span></td>
        <td>${s.is_active ? '<span class="badge badge-success">Faol</span>' : '<span class="badge badge-danger">Nofaol</span>'}</td>
        <td>
          <button class="btn btn-secondary btn-sm" onclick="editStop(${JSON.stringify(s).replace(/"/g, '&quot;')})">Tahrirlash</button>
          <button class="btn btn-danger btn-sm" onclick="deleteStop(${s.id})">O‘chirish</button>
        </td>
      </tr>
    `).join('');

    // RENDER ALL STOPS ON REAL MAP
    if (!stopPickerMap) {
      initStopPickerMap();
    }
    renderStopsOnPickerMap(stops);

    // If an admin just added or updated a stop, smoothly fly map to that stop!
    if (lastAddedStopCoord && stopPickerMap) {
      stopPickerMap.flyTo(lastAddedStopCoord, 16, { animate: true, duration: 1.2 });
      lastAddedStopCoord = null;
    }
  } catch (err) {
    showToast("Bekatlarni yuklashda xatolik", "error");
  }
}

function openStopModal(stop = null) {
  document.getElementById("stopFormId").value = stop ? stop.id : "";
  document.getElementById("stopModalTitle").textContent = stop ? "Bekatni Tahrirlash" : "Yangi Bekat";
  document.getElementById("stopNameInput").value = stop ? stop.name : "";
  document.getElementById("stopLatInput").value = stop ? stop.latitude : "";
  document.getElementById("stopLonInput").value = stop ? stop.longitude : "";
  document.getElementById("stopRadiusInput").value = stop ? stop.default_geofence_radius : "100";
  document.getElementById("stopModal").classList.add("active");
}

function editStop(s) {
  openStopModal(s);
  if (stopPickerMap && s.latitude && s.longitude) {
    stopPickerMap.flyTo([s.latitude, s.longitude], 16);
  }
}

async function handleStopSubmit(e) {
  e.preventDefault();
  const id = document.getElementById("stopFormId").value;
  const name = document.getElementById("stopNameInput").value.trim();
  const latitude = parseFloat(document.getElementById("stopLatInput").value);
  const longitude = parseFloat(document.getElementById("stopLonInput").value);
  const default_geofence_radius = parseInt(document.getElementById("stopRadiusInput").value) || 100;

  try {
    const url = id ? `/api/admin/stops/${id}` : "/api/admin/stops";
    const method = id ? "PUT" : "POST";

    const res = await fetch(url, {
      method,
      headers: {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${adminToken}`
      },
      body: JSON.stringify({ name, latitude, longitude, default_geofence_radius })
    });
    const data = await res.json();
    if (!res.ok) {
      showToast(data.detail || "Xatolik yuz berdi", "error");
      return;
    }

    showToast(`✅ Bekat "${name}" muvaffaqiyatli saqlandi va xaritaga qo'shildi!`, "success");
    closeModal("stopModal");

    // Remove the temporary picker marker
    if (stopPickerMarker && stopPickerMap) {
      stopPickerMap.removeLayer(stopPickerMarker);
      stopPickerMarker = null;
    }

    // Save coordinate to center map on the newly added stop
    lastAddedStopCoord = [latitude, longitude];

    // Reload stops and immediately render on map!
    await loadStops();
  } catch (err) {
    showToast("Server bilan aloqa uzildi", "error");
  }
}

async function deleteStop(id) {
  if (!confirm("Haqiqatan ham ushbu bekatni o‘chirmoqchimisiz?")) return;
  try {
    const res = await fetch(`/api/admin/stops/${id}`, {
      method: "DELETE",
      headers: { "Authorization": `Bearer ${adminToken}` }
    });
    if (res.ok) {
      showToast("Bekat o‘chirildi", "success");
      loadStops();
    }
  } catch (err) {
    showToast("Xatolik", "error");
  }
}

// 6. DRIVERS & PASSWORDS MANAGEMENT
async function loadDrivers() {
  try {
    const res = await fetch("/api/admin/drivers", {
      headers: { "Authorization": `Bearer ${adminToken}` }
    });
    const data = await res.json();
    const drivers = data.drivers || [];
    const tbody = document.getElementById("driversTableBody");

    tbody.innerHTML = drivers.map(d => {
      const lastLogin = d.last_login 
        ? new Date(d.last_login).toLocaleString([], { dateStyle: 'short', timeStyle: 'short' })
        : '<span style="color:var(--text-dim);">Hali kirmagan</span>';

      return `
        <tr>
          <td><code>${d.username}</code></td>
          <td style="font-weight:700;">${d.full_name}</td>
          <td>${d.phone || '—'}</td>
          <td>${d.assigned_route_name ? `${d.route_number}: ${d.assigned_route_name}` : '<span style="color:var(--text-dim);">Biriktirilmagan</span>'}</td>
          <td>${d.assigned_bus_name ? `🚌 ${d.assigned_bus_name} (${d.plate_number})` : '—'}</td>
          <td>${lastLogin}</td>
          <td>${d.is_active ? '<span class="badge badge-success">Faol</span>' : '<span class="badge badge-danger">Bloklangan</span>'}</td>
          <td>
            <button class="btn btn-secondary btn-sm" onclick="openPasswordModal(${d.id}, '${d.full_name}')">🔑 Parolni Reset Qilish</button>
            <button class="btn btn-secondary btn-sm" onclick="editDriver(${JSON.stringify(d).replace(/"/g, '&quot;')})">Tahrirlash</button>
          </td>
        </tr>
      `;
    }).join('');
  } catch (err) {
    showToast("Haydovchilarni yuklashda xatolik", "error");
  }
}

async function openDriverModal(driver = null) {
  // Populate route select options
  const routesRes = await fetch("/api/admin/routes", { headers: { "Authorization": `Bearer ${adminToken}` } });
  const routesData = await routesRes.json();
  const routeSelect = document.getElementById("driverRouteSelect");
  routeSelect.innerHTML = '<option value="0">Yo‘nalish tanlanmagan</option>' +
    (routesData.routes || []).map(r => `<option value="${r.id}">${r.route_number}: ${r.name}</option>`).join('');

  document.getElementById("driverFormId").value = driver ? driver.id : "";
  document.getElementById("driverModalTitle").textContent = driver ? "Haydovchini Tahrirlash" : "Yangi Haydovchi Hisobi";
  document.getElementById("driverFullNameInput").value = driver ? driver.full_name : "";
  document.getElementById("driverPhoneInput").value = driver ? (driver.phone || "") : "";

  const uGroup = document.getElementById("driverUsernameGroup");
  const pGroup = document.getElementById("driverPasswordGroup");

  if (driver) {
    uGroup.style.display = "none";
    pGroup.style.display = "none";
    if (driver.assigned_route_id) routeSelect.value = driver.assigned_route_id;
  } else {
    uGroup.style.display = "block";
    pGroup.style.display = "block";
    document.getElementById("driverUsernameInput").value = "";
    document.getElementById("driverPasswordInput").value = "";
  }

  document.getElementById("driverModal").classList.add("active");
}

function editDriver(d) {
  openDriverModal(d);
}

async function handleDriverSubmit(e) {
  e.preventDefault();
  const id = document.getElementById("driverFormId").value;
  const full_name = document.getElementById("driverFullNameInput").value.trim();
  const phone = document.getElementById("driverPhoneInput").value.trim();
  const route_id = parseInt(document.getElementById("driverRouteSelect").value) || null;

  try {
    let res, data;
    if (id) {
      res = await fetch(`/api/admin/drivers/${id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json", "Authorization": `Bearer ${adminToken}` },
        body: JSON.stringify({ full_name, phone, route_id })
      });
    } else {
      const username = document.getElementById("driverUsernameInput").value.trim();
      const password = document.getElementById("driverPasswordInput").value;
      res = await fetch("/api/admin/drivers", {
        method: "POST",
        headers: { "Content-Type": "application/json", "Authorization": `Bearer ${adminToken}` },
        body: JSON.stringify({ username, password, full_name, phone, route_id })
      });
    }

    data = await res.json();
    if (!res.ok) {
      showToast(data.detail || "Xatolik yuz berdi", "error");
      return;
    }

    showToast("Haydovchi ma'lumotlari saqlandi", "success");
    closeModal("driverModal");
    loadDrivers();
  } catch (err) {
    showToast("Server bilan aloqa uzildi", "error");
  }
}

function openPasswordModal(driverId, driverName) {
  document.getElementById("resetDriverId").value = driverId;
  document.getElementById("resetDriverName").textContent = driverName;
  document.getElementById("newPasswordInput").value = "";
  document.getElementById("passwordModal").classList.add("active");
}

async function handlePasswordReset(e) {
  e.preventDefault();
  const driverId = document.getElementById("resetDriverId").value;
  const new_password = document.getElementById("newPasswordInput").value;

  try {
    const res = await fetch(`/api/admin/drivers/${driverId}/reset-password`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "Authorization": `Bearer ${adminToken}` },
      body: JSON.stringify({ new_password })
    });
    const data = await res.json();
    if (!res.ok) {
      showToast(data.detail || "Parolni o'zgartirishda xatolik", "error");
      return;
    }

    showToast("Parol muvaffaqiyatli yangilandi va xeshlandi (bcrypt)", "success");
    closeModal("passwordModal");
  } catch (err) {
    showToast("Xatolik", "error");
  }
}

// 7. TELEGRAM SETTINGS & LOGS
async function loadTelegramSettings() {
  try {
    const res = await fetch("/api/admin/telegram/settings", {
      headers: { "Authorization": `Bearer ${adminToken}` }
    });
    const data = await res.json();
    if (data.masked_token) {
      document.getElementById("tgBotTokenInput").placeholder = data.masked_token;
    }
    document.getElementById("tgChatIdInput").value = data.default_chat_id || "";
    document.getElementById("testChatIdInput").value = data.default_chat_id || "";
  } catch (err) {
    console.error("TG load err:", err);
  }
}

async function saveTelegramSettings(e) {
  e.preventDefault();
  const bot_token = document.getElementById("tgBotTokenInput").value.trim();
  const default_chat_id = document.getElementById("tgChatIdInput").value.trim();

  try {
    const res = await fetch("/api/admin/telegram/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json", "Authorization": `Bearer ${adminToken}` },
      body: JSON.stringify({ bot_token, default_chat_id })
    });
    if (res.ok) {
      showToast("Telegram sozlamalari muvaffaqiyatli saqlandi", "success");
      loadTelegramSettings();
    }
  } catch (err) {
    showToast("Xatolik yuz berdi", "error");
  }
}

async function sendTestTelegramMessage() {
  const chat_id = document.getElementById("testChatIdInput").value.trim();
  if (!chat_id) {
    showToast("Iltimos, guruh Chat IDsini kiriting", "warning");
    return;
  }

  try {
    showToast("Sinov xabari yuborilmoqda...", "info");
    const res = await fetch("/api/admin/telegram/test", {
      method: "POST",
      headers: { "Content-Type": "application/json", "Authorization": `Bearer ${adminToken}` },
      body: JSON.stringify({ chat_id })
    });
    const data = await res.json();
    if (!res.ok) {
      showToast(data.detail || "Telegram xatosi", "error");
      return;
    }

    showToast("Sinov xabari Telegram guruhga yetkazildi!", "success");
    loadTelegramLogs();
  } catch (err) {
    showToast("Xatolik yuz berdi", "error");
  }
}

async function loadTelegramLogs() {
  try {
    const res = await fetch("/api/admin/telegram/logs", {
      headers: { "Authorization": `Bearer ${adminToken}` }
    });
    const data = await res.json();
    const logs = data.logs || [];
    const tbody = document.getElementById("tgLogsTableBody");

    if (logs.length === 0) {
      tbody.innerHTML = '<tr><td colspan="4" style="text-align:center; color:var(--text-muted);">Xabarlar jurnali bo‘sh</td></tr>';
      return;
    }

    tbody.innerHTML = logs.map(l => {
      const badge = l.status === 'sent'
        ? '<span class="badge badge-success">Yuborildi</span>'
        : (l.status === 'pending' ? '<span class="badge badge-warning">Navbatda</span>' : '<span class="badge badge-danger">Xato</span>');

      return `
        <tr>
          <td><small>${new Date(l.created_at).toLocaleTimeString()}</small></td>
          <td><b>${l.route_name || 'Umumiy'}</b>: ${l.stop_name || 'Xabar'}</td>
          <td>${badge}</td>
          <td>${l.attempts}/3</td>
        </tr>
      `;
    }).join('');
  } catch (err) {
    console.error("TG logs err:", err);
  }
}

// 8. TRIPS HISTORY
async function loadTrips() {
  try {
    const res = await fetch("/api/admin/trips", {
      headers: { "Authorization": `Bearer ${adminToken}` }
    });
    const data = await res.json();
    const trips = data.trips || [];
    const tbody = document.getElementById("tripsTableBody");

    tbody.innerHTML = trips.map(t => {
      const badge = t.status === 'active'
        ? '<span class="badge badge-success"><span class="pulse-dot"></span> Davom etmoqda</span>'
        : '<span class="badge badge-gray">Yakunlangan</span>';

      return `
        <tr>
          <td>#${t.id}</td>
          <td><b>${t.route_number}: ${t.route_name}</b></td>
          <td>🚌 ${t.bus_name} (${t.plate_number})</td>
          <td>👤 ${t.driver_name}</td>
          <td>${new Date(t.start_time).toLocaleString([], { dateStyle:'short', timeStyle:'short' })}</td>
          <td>${t.end_time ? new Date(t.end_time).toLocaleTimeString() : '—'}</td>
          <td><span class="badge badge-info">${t.arrived_stops_count} bekat</span></td>
          <td>${badge}</td>
        </tr>
      `;
    }).join('');
  } catch (err) {
    showToast("Safarlar tarixini yuklashda xatolik", "error");
  }
}

// 9. AUDIT LOGS
async function loadAuditLogs() {
  try {
    const res = await fetch("/api/admin/audit-logs", {
      headers: { "Authorization": `Bearer ${adminToken}` }
    });
    const data = await res.json();
    const logs = data.logs || [];
    const tbody = document.getElementById("auditTableBody");

    tbody.innerHTML = logs.map(a => `
      <tr>
        <td><small>${new Date(a.created_at).toLocaleString([], { dateStyle:'short', timeStyle:'short' })}</small></td>
        <td><b>${a.username || 'Tizim'}</b></td>
        <td><code>${a.action}</code></td>
        <td>${a.entity_type} #${a.entity_id || ''}</td>
        <td>${a.details || ''}</td>
        <td><small style="color:var(--text-muted);">${a.ip_address || '—'}</small></td>
      </tr>
    `).join('');
  } catch (err) {
    showToast("Audit jurnalini yuklashda xatolik", "error");
  }
}

// MODAL HELPERS
function closeModal(modalId) {
  document.getElementById(modalId).classList.remove("active");
}
