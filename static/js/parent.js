// Parent Live Tracking Controller with Full-Screen Map & Instant On-Site Announcements

let map = null;
let currentRouteId = null;
let routesData = [];
let routePolyline = null;
let stopMarkers = [];
let busMarker = null;
let refreshInterval = null;

let autoFollow = true;
let knownArrivalIds = new Set();
let siteAnnouncements = [];

const FERGANA_CENTER = [40.386400, 71.786400];
const SCHOOL_COORDS = [40.386400, 71.786400];
let schoolMarker = null;

document.addEventListener("DOMContentLoaded", () => {
  initMap();
  loadRoutes();

  // Polling every 3.5 seconds for fresh GPS and arrival alerts
  refreshInterval = setInterval(() => {
    if (currentRouteId) {
      loadRouteDetail(currentRouteId, false);
    }
  }, 3500);
});

function initMap() {
  // Tile Layers: OpenStreetMap (Free, No API key), Esri Satellite & Esri Streets
  const osmLayer = L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    maxZoom: 19
  });

  const satelliteLayer = L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", {
    attribution: 'Tiles &copy; Esri &mdash; Source: Esri, i-cubed, USDA, USGS, AEX, GeoEye, Getmapping, Aerogrid, IGN, IGP',
    maxZoom: 19
  });

  const esriStreets = L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}", {
    attribution: 'Tiles &copy; Esri',
    maxZoom: 19
  });

  map = L.map("parentMap", {
    center: FERGANA_CENTER,
    zoom: 14,
    zoomControl: false,
    layers: [osmLayer] // default active layer (100% free, no key required)
  });

  // Layer control switcher (Real Map / Satellite)
  const baseMaps = {
    "🌐 Haqiqiy Xarita (OSM)": osmLayer,
    "🛰️ Sun‘iy Yo‘ldosh (Satellite)": satelliteLayer,
    "🗺️ Esri Ko‘cha Xaritasi": esriStreets
  };
  L.control.layers(baseMaps, null, { position: 'topright' }).addTo(map);

  // Zoom control on bottom right
  L.control.zoom({ position: 'bottomright' }).addTo(map);

  // Permanent Central School Marker in Fergana
  const schoolIcon = L.divIcon({
    className: "school-marker-icon",
    html: `<span>🏫</span>`,
    iconSize: [36, 36],
    iconAnchor: [18, 18]
  });

  schoolMarker = L.marker(SCHOOL_COORDS, { icon: schoolIcon })
    .bindPopup(`
      <div style="font-family:inherit; padding:2px;">
        <b style="color:#ef4444; font-size:1.05rem;">🏫 Farg‘ona Bosh Maktabi (№1)</b><br>
        <span style="font-size:0.85rem; color:#475569;">📍 Al-Farg‘oniy / Sayilgoh ko‘chasi, Farg‘ona shahri</span><br>
        <span style="font-size:0.8rem; color:#10b981; font-weight:600;">✓ Barcha maktab avtobuslari manzili</span>
      </div>
    `)
    .addTo(map);

  // If user drags the map manually, turn off autoFollow so we don't snap back abruptly
  map.on("dragstart", () => {
    if (autoFollow) {
      setAutoFollow(false);
    }
  });
}

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

async function loadRoutes() {
  try {
    const res = await fetch("/api/public/routes");
    const data = await res.json();
    routesData = data.routes || [];

    populateRouteDropdown(routesData);

    // Check URL parameters for direct link (?route=3)
    const urlParams = new URLSearchParams(window.location.search);
    const paramRouteId = parseInt(urlParams.get("route"));

    if (paramRouteId && routesData.some(r => r.id === paramRouteId)) {
      selectRoute(paramRouteId);
    } else if (routesData.length > 0) {
      selectRoute(routesData[0].id);
    }
  } catch (err) {
    console.error("Yo'nalishlarni yuklashda xatolik:", err);
  }
}

function populateRouteDropdown(routes) {
  const select = document.getElementById("routeSelectDropdown");
  if (!routes || routes.length === 0) {
    select.innerHTML = '<option value="">Yo‘nalishlar mavjud emas</option>';
    return;
  }

  select.innerHTML = routes.map(r => `
    <option value="${r.id}">
      ${r.route_number}: ${r.name} (${r.is_in_trip ? '🟢 Safarda' : '⚪ Kutmoqda'})
    </option>
  `).join('');
}

function onRouteDropdownChange(val) {
  const routeId = parseInt(val);
  if (routeId) {
    selectRoute(routeId);
    // Update browser URL query without reloading
    const newUrl = `${window.location.pathname}?route=${routeId}`;
    window.history.pushState({ path: newUrl }, '', newUrl);
  }
}

function selectRoute(routeId) {
  currentRouteId = routeId;
  const dropdown = document.getElementById("routeSelectDropdown");
  if (dropdown) dropdown.value = routeId;

  // Reset known arrivals for this route
  knownArrivalIds.clear();
  loadRouteDetail(routeId, true);
}

async function loadRouteDetail(routeId, fitBoundsInitial = false) {
  try {
    const res = await fetch(`/api/public/routes/${routeId}`);
    if (!res.ok) return;
    const data = await res.json();

    updateRouteUI(data);
    drawRouteOnMap(data, fitBoundsInitial);
    checkNewArrivalAnnouncements(data);
  } catch (err) {
    console.error("Tafsilotlarni yuklashda xatolik:", err);
  }
}

function updateRouteUI(data) {
  const { route, trip, latest_gps, is_gps_stale, next_stop, arrivals, stops } = data;

  document.getElementById("sidebarRouteTitle").textContent = `${route.route_number}: ${route.name}`;
  document.getElementById("busPlateText").textContent = route.plate_number ? `${route.bus_name} (${route.plate_number})` : "Biriktirilmagan";

  const liveBadge = document.getElementById("routeLiveBadge");
  const tripStatusText = document.getElementById("busTripStatusText");
  const nextStopText = document.getElementById("nextStopNameText");
  const gpsTimeText = document.getElementById("gpsLastTimeText");

  if (trip && trip.status === 'active') {
    if (is_gps_stale) {
      liveBadge.className = "badge badge-warning";
      liveBadge.innerHTML = "⚠️ GPS uzildi";
      tripStatusText.textContent = "Aloqa kutilmoqda";
      tripStatusText.style.color = "#f59e0b";
    } else {
      liveBadge.className = "badge badge-success";
      liveBadge.innerHTML = '<span class="pulse-dot"></span> Jonli Harakatda';
      tripStatusText.textContent = "Yo‘lda ketmoqda";
      tripStatusText.style.color = "#34d399";
    }

    if (next_stop) {
      nextStopText.textContent = `${next_stop.order}-bekat: ${next_stop.name}`;
    } else {
      nextStopText.textContent = "Oxirgi bekat / Maktab";
    }

    if (latest_gps) {
      const timeStr = new Date(latest_gps.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
      gpsTimeText.textContent = `${timeStr} (${Math.round(latest_gps.speed || 0)} km/s)`;
    } else {
      gpsTimeText.textContent = "Kutilmoqda";
    }
  } else {
    liveBadge.className = "badge badge-gray";
    liveBadge.innerHTML = "Safarda emas";
    tripStatusText.textContent = "To‘xtab turibdi";
    tripStatusText.style.color = "var(--text-muted)";
    nextStopText.textContent = stops.length > 0 ? stops[0].name : "Mavjud emas";
    gpsTimeText.textContent = "—";
  }

  // Recent visited note
  const noteEl = document.getElementById("recentArrivalNote");
  if (arrivals && arrivals.length > 0) {
    const lastArr = arrivals[arrivals.length - 1];
    const arrTime = new Date(lastArr.arrived_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    noteEl.innerHTML = `📍 <b>So‘nggi bekat:</b> ${lastArr.stop_name} <span style="color:#10b981;">(${arrTime})</span>`;
  } else {
    noteEl.innerHTML = `📍 Hozircha bekatlarga yetib kelish qayd etilmadi`;
  }

  // Update Desktop Bottom Timeline
  updateDesktopTimeline(stops, arrivals, next_stop);
}

function updateDesktopTimeline(stops, arrivals, next_stop) {
  const container = document.getElementById("desktopTimelineScroll");
  if (!stops || stops.length === 0) {
    container.innerHTML = '<div style="color:var(--text-muted);">Bekatlar mavjud emas</div>';
    return;
  }

  const arrivalMap = {};
  (arrivals || []).forEach(a => { arrivalMap[a.stop_id] = a.arrived_at; });

  container.innerHTML = stops.map((s, idx) => {
    const isVisited = !!arrivalMap[s.id];
    const isNext = next_stop && next_stop.id === s.id;

    let cls = "timeline-node";
    let statusLabel = `<span style="color:var(--text-dim);">${idx + 1}-bekat</span>`;

    if (isVisited) {
      cls += " visited";
      const timeStr = new Date(arrivalMap[s.id]).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
      statusLabel = `<span style="color:#10b981; font-weight:700;">✓ Kelindi (${timeStr})</span>`;
    } else if (isNext) {
      cls += " next";
      statusLabel = `<span style="color:#f59e0b; font-weight:700;">⏳ Kutilmoqda</span>`;
    }

    return `
      <div class="${cls}">
        <div style="display:flex; justify-content:space-between; margin-bottom:0.25rem;">
          ${statusLabel}
          <span style="font-size:0.75rem; color:var(--text-dim);">${s.estimated_minutes} daq</span>
        </div>
        <div style="font-weight:700; color:#fff; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;" title="${s.name}">
          ${s.name}
        </div>
      </div>
    `;
  }).join('');
}

// CHECK FOR NEW ON-SITE ARRIVAL ANNOUNCEMENTS (Trigger banner + chime)
function checkNewArrivalAnnouncements(data) {
  const { arrivals, route } = data;
  if (!arrivals || arrivals.length === 0) return;

  arrivals.forEach(arr => {
    if (!knownArrivalIds.has(arr.stop_id)) {
      knownArrivalIds.add(arr.stop_id);

      const timeStr = new Date(arr.arrived_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
      const announcement = {
        id: arr.stop_id,
        title: `🚌 Bekatga kelindi: ${arr.stop_name}`,
        desc: `${route.route_number} avtobusi soat ${timeStr}da yetib keldi.`,
        time: timeStr
      };

      siteAnnouncements.unshift(announcement);
      updateAnnouncementsDrawer();

      // Trigger pop-up alert banner on site!
      triggerAlertBanner(
        `AVTOBUS BEKATGA YETIB KELDI! (${timeStr})`,
        `${route.route_number}: Avtobus "${arr.stop_name}" bekatida bolalarni kutmoqda.`
      );

      // Play audio notification chime
      playChimeAudio();
    }
  });
}

function triggerAlertBanner(title, text) {
  const banner = document.getElementById("liveAlertBanner");
  document.getElementById("alertBannerTitle").textContent = title;
  document.getElementById("alertBannerText").textContent = text;

  banner.classList.add("active");
  setTimeout(() => {
    banner.classList.remove("active");
  }, 9000);
}

function dismissAlertBanner() {
  document.getElementById("liveAlertBanner").classList.remove("active");
}

function playChimeAudio() {
  try {
    const audio = document.getElementById("parentDingAudio");
    if (audio) {
      audio.currentTime = 0;
      audio.play().catch(() => {});
    }
  } catch (e) {}
}

function updateAnnouncementsDrawer() {
  const listEl = document.getElementById("announcementsList");
  const countBadge = document.getElementById("feedCountBadge");
  countBadge.textContent = siteAnnouncements.length;

  if (siteAnnouncements.length === 0) {
    listEl.innerHTML = '<div style="color:var(--text-muted); font-size:0.85rem; text-align:center; padding:1.5rem 0;">Hozircha xabarlar yo‘q</div>';
    return;
  }

  listEl.innerHTML = siteAnnouncements.map(a => `
    <div style="background:rgba(15,23,42,0.8); border:1px solid rgba(255,255,255,0.06); border-radius:var(--radius-md); padding:0.65rem 0.85rem;">
      <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:0.25rem;">
        <span style="font-weight:700; font-size:0.85rem; color:#34d399;">${a.title}</span>
        <span style="font-size:0.75rem; color:var(--text-muted);">${a.time}</span>
      </div>
      <div style="font-size:0.8rem; color:#cbd5e1;">${a.desc}</div>
    </div>
  `).join('');
}

function toggleAnnouncementsFeed() {
  const drawer = document.getElementById("announcementsDrawer");
  drawer.classList.toggle("open");
}

// DRAW ROUTE ON MAP
function drawRouteOnMap(data, fitBoundsInitial = false) {
  const { stops, latest_gps, visited_stop_ids, next_stop, trip } = data;

  // Clear previous stop markers & polyline
  stopMarkers.forEach(m => map.removeLayer(m));
  stopMarkers = [];
  if (routePolyline) {
    map.removeLayer(routePolyline);
    routePolyline = null;
  }

  if (!stops || stops.length === 0) return;

  const latlngs = stops.map(s => [s.latitude, s.longitude]);

  // Dynamic route line with vibrant styling
  routePolyline = L.polyline(latlngs, {
    color: "#6366f1",
    weight: 6,
    opacity: 0.85,
    dashArray: "1, 10",
    lineCap: "round"
  }).addTo(map);

  // Add stop markers
  stops.forEach((s, idx) => {
    const isVisited = visited_stop_ids && visited_stop_ids.includes(s.id);
    const isNext = next_stop && next_stop.id === s.id;

    let iconCls = "stop-marker-icon";
    let iconHtml = `${idx + 1}`;

    if (isVisited) {
      iconCls += " visited";
      iconHtml = "✓";
    } else if (isNext) {
      iconCls += " next";
      iconHtml = "📍";
    }

    const customIcon = L.divIcon({
      className: iconCls,
      html: `<span>${iconHtml}</span>`,
      iconSize: [28, 28],
      iconAnchor: [14, 14]
    });

    const marker = L.marker([s.latitude, s.longitude], { icon: customIcon })
      .bindPopup(`<b>${idx + 1}-bekat:</b> ${s.name}`)
      .addTo(map);

    stopMarkers.push(marker);
  });

  // Bus Marker: Always display bus on map (live position if moving, or at Start stop if waiting)
  let busPos = null;
  let isLiveMoving = false;
  let heading = 0;
  let busSpeed = 0;
  let busTime = null;

  if (trip && latest_gps && latest_gps.latitude && latest_gps.longitude) {
    busPos = [latest_gps.latitude, latest_gps.longitude];
    isLiveMoving = true;
    heading = latest_gps.heading || 0;
    busSpeed = Math.round(latest_gps.speed || 0);
    busTime = new Date(latest_gps.timestamp).toLocaleTimeString();
  } else if (stops && stops.length > 0) {
    // If trip not active yet, bus is stationed at Route's Start Stop #1
    busPos = [stops[0].latitude, stops[0].longitude];
    isLiveMoving = false;
    heading = 0;
    busSpeed = 0;
  }

  if (busPos) {
    const busIcon = L.divIcon({
      className: "smooth-bus-marker",
      html: `
        <div class="yandex-bus-icon-wrap">
          ${isLiveMoving ? '<div class="yandex-bus-radar"></div>' : ''}
          <div class="yandex-bus-body" id="parentBusRotator" style="transform: rotate(${Math.round(heading)}deg); ${!isLiveMoving ? 'background: linear-gradient(135deg, #0284c7, #3b82f6);' : ''}">
            🚌
          </div>
        </div>
      `,
      iconSize: [44, 44],
      iconAnchor: [22, 22]
    });

    if (!busMarker) {
      busMarker = L.marker(busPos, { icon: busIcon }).addTo(map);
    } else {
      busMarker.setIcon(busIcon);
      busMarker.setLatLng(busPos);
      const rot = document.getElementById("parentBusRotator");
      if (rot) rot.style.transform = `rotate(${Math.round(heading)}deg)`;
    }

    if (isLiveMoving) {
      busMarker.bindPopup(`
        <b>🚌 Maktab Avtobusi (Jonli Yo‘lda)</b><br>
        Tezlik: ${busSpeed} km/soat<br>
        Oxirgi GPS: ${busTime}
      `);
      if (autoFollow) {
        map.panTo(busPos, { animate: true, duration: 1.0 });
      }
    } else {
      busMarker.bindPopup(`
        <b>🚌 Maktab Avtobusi</b><br>
        Holat: 🅿️ 1-Bekatda kutmoqda (Start nuqtasida)<br>
        Yo‘nalish: ${data.route ? data.route.name : ''}
      `);
    }
  } else {
    if (busMarker) {
      map.removeLayer(busMarker);
      busMarker = null;
    }
  }

  if (fitBoundsInitial) {
    fitRouteBounds();
  }
}

function fitRouteBounds() {
  if (routePolyline) {
    map.fitBounds(routePolyline.getBounds(), { padding: [80, 80] });
  }
}

function toggleAutoFollow() {
  setAutoFollow(!autoFollow);
}

function setAutoFollow(val) {
  autoFollow = val;
  const btn = document.getElementById("autoFollowBtn");
  const label = document.getElementById("autoFollowLabel");

  if (autoFollow) {
    btn.classList.add("active");
    label.textContent = "Avtobusni Kuzatish: YOQILGAN";
    if (busMarker) {
      map.panTo(busMarker.getLatLng(), { animate: true });
    }
    showToast("Avtobusni avtomatik kuzatish rejimi faollashdi", "info");
  } else {
    btn.classList.remove("active");
    label.textContent = "Avtobusni Kuzatish: O‘CHIRILGAN";
    showToast("Xarita erkin ko‘rish rejimiga o‘tdi", "info");
  }
}

// COPY DIRECT ROUTE LINK TO SHARE WITH PARENTS
function copyCurrentRouteLink() {
  const url = `${window.location.origin}/parent?route=${currentRouteId}`;
  navigator.clipboard.writeText(url).then(() => {
    showToast("✅ Yo‘nalish havolasi nusxalandi! Ota-onalar bilan ulashishingiz mumkin.", "success");
  }).catch(() => {
    prompt("Ushbu havolani nusxalab oling:", url);
  });
}
