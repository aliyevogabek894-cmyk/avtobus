// Driver Mobile Controller with Persistent Background Geolocation & Audio Keepalive

let driverToken = localStorage.getItem("sb_driver_token");
let driverUser = null;
let assignedData = null; // route, stops, active_trip
let activeTripId = localStorage.getItem("sb_driver_active_trip_id") ? parseInt(localStorage.getItem("sb_driver_active_trip_id")) : null;

let driverMap = null;
let busMarker = null;
let routePolyline = null;
let stopMarkers = [];

let watchPositionId = null;
let bgGpsIntervalId = null;
let wakeLock = null;

// Simulator mode state
let isSimMode = false;
let simIndex = 0;
let simAutoInterval = null;
let lastKnownCoords = null;

document.addEventListener("DOMContentLoaded", () => {
  if (driverToken) {
    checkDriverAuth();
  } else {
    showLogin();
  }

  // Handle visibility change (when driver switches apps or comes back)
  document.addEventListener("visibilitychange", () => {
    if (activeTripId && !document.hidden) {
      // Re-trigger location immediately when returning to tab
      if (lastKnownCoords) {
        sendGpsToServer(lastKnownCoords.lat, lastKnownCoords.lon, lastKnownCoords.speed || 0, 0, 10);
      }
    }
  });
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

function showLogin() {
  document.getElementById("loginSection").style.display = "block";
  document.getElementById("driverDashboard").style.display = "none";
  document.getElementById("logoutBtn").style.display = "none";
  document.getElementById("driverHeaderName").textContent = "Tizimga kiring";
}

function showDashboard() {
  document.getElementById("loginSection").style.display = "none";
  document.getElementById("driverDashboard").style.display = "flex";
  document.getElementById("logoutBtn").style.display = "inline-flex";
  if (driverUser) {
    document.getElementById("driverHeaderName").textContent = driverUser.full_name || driverUser.username;
  }
}

async function handleDriverLogin(e) {
  e.preventDefault();
  const username = document.getElementById("loginUsername").value.trim();
  const password = document.getElementById("loginPassword").value;

  try {
    const res = await fetch("/api/driver/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password })
    });

    const data = await res.json();
    if (!res.ok) {
      showToast(data.detail || "Kirishda xatolik yuz berdi", "error");
      return;
    }

    driverToken = data.token;
    driverUser = data.user;
    localStorage.setItem("sb_driver_token", driverToken);
    localStorage.setItem("sb_driver_user", JSON.stringify(driverUser));

    showToast("Tizimga muvaffaqiyatli kirildi", "success");
    showDashboard();
    initDriverMap();
    loadMyRoute();
  } catch (err) {
    showToast("Server bilan aloqa uzildi", "error");
  }
}

function driverLogout() {
  stopGpsTracking();
  localStorage.removeItem("sb_driver_token");
  localStorage.removeItem("sb_driver_user");
  localStorage.removeItem("sb_driver_active_trip_id");
  driverToken = null;
  driverUser = null;
  activeTripId = null;
  showLogin();
}

async function checkDriverAuth() {
  try {
    const userStr = localStorage.getItem("sb_driver_user");
    if (userStr) driverUser = JSON.parse(userStr);
    showDashboard();
    initDriverMap();
    await loadMyRoute();
  } catch (err) {
    driverLogout();
  }
}

const FERGANA_CENTER = [40.386400, 71.786400];
const SCHOOL_COORDS = [40.386400, 71.786400];
let driverSchoolMarker = null;

function initDriverMap() {
  if (driverMap) return;

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

  driverMap = L.map("driverMap", {
    center: FERGANA_CENTER,
    zoom: 14,
    zoomControl: false,
    layers: [osmLayer]
  });

  // Zoom control
  L.control.zoom({ position: 'bottomright' }).addTo(driverMap);

  // Layer control switcher
  const baseMaps = {
    "🌐 Haqiqiy Xarita (OSM)": osmLayer,
    "🛰️ Sun‘iy Yo‘ldosh (Satellite)": satelliteLayer,
    "🗺️ Esri Ko‘cha Xaritasi": esriStreets
  };
  L.control.layers(baseMaps, null, { position: 'topright' }).addTo(driverMap);

  // School marker in Fergana
  const schoolIcon = L.divIcon({
    className: "school-marker-icon",
    html: `<span>🏫</span>`,
    iconSize: [34, 34],
    iconAnchor: [17, 17]
  });

  driverSchoolMarker = L.marker(SCHOOL_COORDS, { icon: schoolIcon })
    .bindPopup(`<b>🏫 Farg‘ona Bosh Maktabi (№1)</b><br>Manzil: Al-Farg‘oniy ko‘chasi`)
    .addTo(driverMap);
}

async function loadMyRoute() {
  try {
    const res = await fetch("/api/driver/my-route", {
      headers: { "Authorization": `Bearer ${driverToken}` }
    });
    if (!res.ok) {
      if (res.status === 401) { driverLogout(); return; }
      return;
    }

    assignedData = await res.json();
    const { route, stops, active_trip } = assignedData;

    if (!route) {
      showToast("Sizga faol yo‘nalish biriktirilmagan. Administratorga murojaat qiling.", "error");
      document.getElementById("driverRouteName").textContent = "Yo‘nalish biriktirilmagan";
      return;
    }

    document.getElementById("driverRouteNumber").textContent = route.route_number;
    document.getElementById("driverRouteName").textContent = route.name;
    document.getElementById("driverBusPlate").textContent = `Avtobus: ${route.bus_name} (${route.plate_number})`;

    drawRouteOnDriverMap(stops);

    if (active_trip) {
      activeTripId = active_trip.id;
      localStorage.setItem("sb_driver_active_trip_id", activeTripId);
      setTripActiveUI(true);
      if (active_trip.next_stop_name) {
        document.getElementById("nextStopName").textContent = active_trip.next_stop_name;
      }
      startGpsTracking();
    } else {
      activeTripId = null;
      localStorage.removeItem("sb_driver_active_trip_id");
      setTripActiveUI(false);
      if (stops.length > 0) {
        document.getElementById("nextStopName").textContent = stops[0].name;
        document.getElementById("nextStopSub").textContent = "1-bekat (Start nuqtasi)";
      }
    }
  } catch (err) {
    console.error("Yo'nalish ma'lumotlarini yuklashda xatolik:", err);
  }
}

function setTripActiveUI(isActive) {
  const startBtn = document.getElementById("startTripBtn");
  const endBtn = document.getElementById("endTripBtn");
  const gpsPill = document.getElementById("gpsStatusPill");
  const bgAlert = document.getElementById("bgKeepAliveAlert");

  if (isActive) {
    startBtn.style.display = "none";
    endBtn.style.display = "flex";
    gpsPill.className = "badge badge-success";
    gpsPill.innerHTML = '<span class="pulse-dot"></span> Jonli GPS Faol';
    bgAlert.style.display = "flex";
  } else {
    startBtn.style.display = "flex";
    endBtn.style.display = "none";
    gpsPill.className = "badge badge-gray";
    gpsPill.innerHTML = "GPS To‘xtatilgan";
    bgAlert.style.display = "none";
    document.getElementById("metricSpeed").textContent = "0";
  }
}

function drawRouteOnDriverMap(stops) {
  stopMarkers.forEach(m => driverMap.removeLayer(m));
  stopMarkers = [];
  if (routePolyline) driverMap.removeLayer(routePolyline);

  if (!stops || stops.length === 0) return;

  const latlngs = stops.map(s => [s.latitude, s.longitude]);
  routePolyline = L.polyline(latlngs, {
    color: "#f59e0b",
    weight: 4,
    opacity: 0.8
  }).addTo(driverMap);

  stops.forEach((s, idx) => {
    const icon = L.divIcon({
      className: "stop-marker-icon",
      html: `<span>${idx + 1}</span>`,
      iconSize: [22, 22],
      iconAnchor: [11, 11]
    });
    const m = L.marker([s.latitude, s.longitude], { icon }).addTo(driverMap);
    stopMarkers.push(m);
  });

  driverMap.fitBounds(routePolyline.getBounds(), { padding: [30, 30] });

  // If busMarker not yet placed, station it at Start Stop #1
  if (stops.length > 0 && !busMarker) {
    updateDriverPosition(stops[0].latitude, stops[0].longitude, 0, 10, 0);
  }
}

async function startTrip() {
  try {
    const res = await fetch("/api/driver/trip/start", {
      method: "POST",
      headers: { "Authorization": `Bearer ${driverToken}` }
    });
    const data = await res.json();
    if (!res.ok) {
      showToast(data.detail || "Safarni boshlashda xatolik", "error");
      return;
    }

    activeTripId = data.trip.id;
    localStorage.setItem("sb_driver_active_trip_id", activeTripId);

    setTripActiveUI(true);
    showToast("Safar boshlandi! Fon rejimida uzatish faollashdi", "success");

    // Enable background audio keepalive & wake lock
    enableBackgroundPersistence();

    startGpsTracking();
  } catch (err) {
    showToast("Server bilan aloqa uzildi", "error");
  }
}

async function endTrip() {
  if (!confirm("Haqiqatan ham ushbu safarni yakunlamoqchimisiz?")) return;

  try {
    const res = await fetch("/api/driver/trip/end", {
      method: "POST",
      headers: { "Authorization": `Bearer ${driverToken}` }
    });
    const data = await res.json();
    if (!res.ok) {
      showToast(data.detail || "Safarni tugatishda xatolik", "error");
      return;
    }

    stopGpsTracking();
    disableBackgroundPersistence();

    activeTripId = null;
    localStorage.removeItem("sb_driver_active_trip_id");
    setTripActiveUI(false);
    showToast("Safar muvaffaqiyatli yakunlandi", "success");
    loadMyRoute();
  } catch (err) {
    showToast("Xatolik yuz berdi", "error");
  }
}

function startGpsTracking() {
  if (isSimMode) return;

  if (!navigator.geolocation) {
    showToast("Qurilmangizda Geolocation mavjud emas. Sinov rejimidan foydalaning.", "warning");
    return;
  }

  // 1. Native watchPosition
  watchPositionId = navigator.geolocation.watchPosition(
    (pos) => {
      const lat = pos.coords.latitude;
      const lon = pos.coords.longitude;
      const speed = (pos.coords.speed || 0) * 3.6; // convert m/s to km/h
      const heading = pos.coords.heading || 0;
      const accuracy = pos.coords.accuracy || 10;

      lastKnownCoords = { lat, lon, speed, heading, accuracy };
      updateDriverPosition(lat, lon, speed, accuracy);
      sendGpsToServer(lat, lon, speed, heading, accuracy);
    },
    (err) => {
      console.warn("GPS Geolocation xatosi:", err.message);
      document.getElementById("gpsStatusPill").className = "badge badge-danger";
      document.getElementById("gpsStatusPill").innerHTML = "⚠️ GPS Xatosi";
    },
    {
      enableHighAccuracy: true,
      maximumAge: 2500,
      timeout: 10000
    }
  );

  // 2. Fallback timer interval (ensures location keeps transmitting even in background tab)
  if (bgGpsIntervalId) clearInterval(bgGpsIntervalId);
  bgGpsIntervalId = setInterval(() => {
    if (activeTripId && !isSimMode && lastKnownCoords) {
      sendGpsToServer(
        lastKnownCoords.lat,
        lastKnownCoords.lon,
        lastKnownCoords.speed || 0,
        lastKnownCoords.heading || 0,
        lastKnownCoords.accuracy || 10
      );
    }
  }, 4000);
}

function stopGpsTracking() {
  if (watchPositionId) {
    navigator.geolocation.clearWatch(watchPositionId);
    watchPositionId = null;
  }
  if (bgGpsIntervalId) {
    clearInterval(bgGpsIntervalId);
    bgGpsIntervalId = null;
  }
  if (simAutoInterval) {
    clearInterval(simAutoInterval);
    simAutoInterval = null;
  }
}

async function sendGpsToServer(latitude, longitude, speed = 0, heading = 0, accuracy = 10) {
  if (!activeTripId) return;

  try {
    const res = await fetch("/api/driver/trip/gps", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${driverToken}`
      },
      body: JSON.stringify({
        trip_id: activeTripId,
        latitude,
        longitude,
        speed,
        heading,
        accuracy
      })
    });

    if (!res.ok) return;
    const data = await res.json();

    if (data.arrival_triggered) {
      handleArrivalEvent(data.arrived_stop_name);
    }

    if (data.next_stop) {
      document.getElementById("nextStopName").textContent = data.next_stop.name;
      document.getElementById("nextStopSub").textContent = `${data.next_stop.order}-bekat`;
      document.getElementById("nextStopDistanceBadge").textContent = `${Math.round(data.distance_to_next || 0)} metr`;
      document.getElementById("metricVisitedCount").textContent = `${data.next_stop.order - 1}/${assignedData.stops.length}`;
    } else {
      document.getElementById("nextStopName").textContent = "Barcha bekatlar bosib o‘tildi!";
      document.getElementById("nextStopSub").textContent = "Maktab manziliga yetib kelindi";
      document.getElementById("nextStopDistanceBadge").textContent = "0 metr";
      document.getElementById("metricVisitedCount").textContent = `${assignedData.stops.length}/${assignedData.stops.length}`;
    }
  } catch (err) {
    console.error("GPS yuborishda xatolik:", err);
  }
}

let smoothRoutePoints = [];
let smoothPointIndex = 0;

function updateDriverPosition(lat, lon, speed = 0, accuracy = 10, heading = 0) {
  document.getElementById("metricSpeed").textContent = Math.round(speed || 0);
  document.getElementById("metricAccuracy").textContent = `${Math.round(accuracy || 10)}m`;

  const pos = [lat, lon];
  const roundedHeading = Math.round(heading || 0);

  if (!busMarker) {
    const busIcon = L.divIcon({
      className: "smooth-bus-marker",
      html: `
        <div class="yandex-bus-icon-wrap">
          <div class="yandex-bus-radar"></div>
          <div class="yandex-bus-body" id="driverBusRotator" style="transform: rotate(${roundedHeading}deg);">
            🚌
          </div>
        </div>
      `,
      iconSize: [44, 44],
      iconAnchor: [22, 22]
    });
    busMarker = L.marker(pos, { icon: busIcon }).addTo(driverMap);
  } else {
    busMarker.setLatLng(pos);
    const rot = document.getElementById("driverBusRotator");
    if (rot) rot.style.transform = `rotate(${roundedHeading}deg)`;
  }

  driverMap.panTo(pos, { animate: true, duration: 0.9 });
}

function handleArrivalEvent(stopName) {
  if (navigator.vibrate) {
    navigator.vibrate([200, 100, 200, 100, 400]);
  }
  try {
    const audio = document.getElementById("arrivalAudio");
    if (audio) audio.play();
  } catch (e) {}

  showToast(`🎉 "${stopName}" bekati aniqlandi! Ota-onalarga va saytga xabar yuborildi.`, "success");
}

// BACKGROUND PERSISTENCE HELPERS
function enableBackgroundPersistence() {
  // 1. Silent Audio to prevent mobile browser tab freezing
  try {
    const silentAudio = document.getElementById("silentAudioLoop");
    if (silentAudio) {
      silentAudio.play().catch(() => {});
    }
  } catch (e) {}

  // 2. Screen Wake Lock
  if ('wakeLock' in navigator) {
    navigator.wakeLock.request('screen').then(lock => {
      wakeLock = lock;
    }).catch(() => {});
  }
}

function disableBackgroundPersistence() {
  try {
    const silentAudio = document.getElementById("silentAudioLoop");
    if (silentAudio) {
      silentAudio.pause();
    }
  } catch (e) {}

  if (wakeLock) {
    wakeLock.release().then(() => { wakeLock = null; }).catch(() => {});
  }
}

// SIMULATOR CONTROLS: YANDEX-STYLE REALISTIC STREET GLIDING
function generateSmoothRoutePoints(stops) {
  if (!stops || stops.length < 2) return [];
  const points = [];

  for (let i = 0; i < stops.length - 1; i++) {
    const s1 = stops[i];
    const s2 = stops[i + 1];

    // 14 intermediate steps between consecutive stops for continuous fluid movement
    const steps = 14;
    const dLat = (s2.latitude - s1.latitude) / steps;
    const dLon = (s2.longitude - s1.longitude) / steps;

    // Calculate heading angle
    const lat1 = s1.latitude * Math.PI / 180;
    const lat2 = s2.latitude * Math.PI / 180;
    const dL = (s2.longitude - s1.longitude) * Math.PI / 180;
    const y = Math.sin(dL) * Math.cos(lat2);
    const x = Math.cos(lat1) * Math.sin(lat2) - Math.sin(lat1) * Math.cos(lat2) * Math.cos(dL);
    const bearing = (Math.atan2(y, x) * 180 / Math.PI + 360) % 360;

    for (let j = 0; j < steps; j++) {
      points.push({
        lat: s1.latitude + dLat * j,
        lon: s1.longitude + dLon * j,
        heading: Math.round(bearing),
        speed: 34 + Math.floor(Math.random() * 12),
        is_stop: j === 0,
        stop_name: s1.name
      });
    }
  }

  const last = stops[stops.length - 1];
  points.push({
    lat: last.latitude,
    lon: last.longitude,
    heading: 0,
    speed: 0,
    is_stop: true,
    stop_name: last.name
  });

  return points;
}

function toggleGpsMode() {
  isSimMode = !isSimMode;
  const simControls = document.getElementById("simControls");
  const modeLabel = document.getElementById("gpsModeLabel");
  const toggleBtn = document.getElementById("toggleSimBtn");

  if (isSimMode) {
    simControls.style.display = "block";
    modeLabel.textContent = "🎮 Jonli Yandex Simulyatori (Silliq Harakat)";
    modeLabel.style.color = "#38bdf8";
    toggleBtn.textContent = "📱 Haqiqiy GPSga qaytish";
    if (watchPositionId) {
      navigator.geolocation.clearWatch(watchPositionId);
      watchPositionId = null;
    }

    if (assignedData && assignedData.stops) {
      smoothRoutePoints = generateSmoothRoutePoints(assignedData.stops);
      smoothPointIndex = 0;
    }

    showToast("Jonli Yandex-uslubidagi harakat simulyatori yoqildi! 'Avtomatik Harakat'ni bosing.", "info");
  } else {
    simControls.style.display = "none";
    modeLabel.textContent = "Haqiqiy qurilma GPS datchigi";
    modeLabel.style.color = "var(--text-muted)";
    toggleBtn.textContent = "🎮 Sinov Simulyatoriga o'tish";
    if (simAutoInterval) {
      clearInterval(simAutoInterval);
      simAutoInterval = null;
    }
    if (activeTripId) startGpsTracking();
  }
}

function simNextStep() {
  if (!assignedData || !assignedData.stops || assignedData.stops.length === 0) return;
  if (!activeTripId) {
    showToast("Avval 'YO‘LNI BOSHLASH' tugmasini bosing!", "warning");
    return;
  }

  if (smoothRoutePoints.length === 0) {
    smoothRoutePoints = generateSmoothRoutePoints(assignedData.stops);
    smoothPointIndex = 0;
  }

  if (smoothPointIndex >= smoothRoutePoints.length) {
    smoothPointIndex = 0;
  }

  const pt = smoothRoutePoints[smoothPointIndex];
  smoothPointIndex++;

  lastKnownCoords = { lat: pt.lat, lon: pt.lon, speed: pt.speed, heading: pt.heading, accuracy: 5 };
  updateDriverPosition(pt.lat, pt.lon, pt.speed, 5, pt.heading);
  sendGpsToServer(pt.lat, pt.lon, pt.speed, pt.heading, 5);
}

function toggleSimAutoPlay() {
  const btn = document.getElementById("simAutoPlayBtn");
  if (simAutoInterval) {
    clearInterval(simAutoInterval);
    simAutoInterval = null;
    btn.textContent = "▶️ Avtomatik Harakat";
    btn.className = "btn btn-secondary btn-sm";
    showToast("Harakat to‘xtatildi", "info");
  } else {
    if (!activeTripId) {
      showToast("Avval 'YO‘LNI BOSHLASH' tugmasini bosing!", "warning");
      return;
    }
    btn.textContent = "⏸️ To‘xtatish";
    btn.className = "btn btn-danger btn-sm";

    if (smoothRoutePoints.length === 0) {
      smoothRoutePoints = generateSmoothRoutePoints(assignedData.stops);
      smoothPointIndex = 0;
    }

    simNextStep();
    // Glide forward smoothly every 1.25 seconds like real Yandex Go car
    simAutoInterval = setInterval(() => {
      simNextStep();
    }, 1250);

    showToast("🚌 Avtobus Yandex kabi ko‘cha bo‘ylab silliq harakatlanishni boshladi!", "success");
  }
}
