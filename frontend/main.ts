import L from "leaflet";
import axios from "axios";
let map: L.Map;
let baseLayer: L.TileLayer;
// ----------------- MAP SETUP -----------------
function initMap() {
  if (map && typeof map.remove === "function") {
    map.remove();
  }

  map = L.map("map", {
    center: [0, 0],
    zoom: 2,
    worldCopyJump: true,   // handles anti-meridian wrap smoothly
    minZoom: 1,
    maxZoom: 19
  });

  baseLayer = L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution:
      'Map data © <a href="https://www.openstreetmap.org/">OpenStreetMap</a> contributors',
    maxNativeZoom: 19,
    maxZoom: 19
    // noWrap: true  <-- removed so the map doesn’t shrink inside grey panel
  }).addTo(map);

  // Avoid zooming too far out
  map.on("zoomend", () => {
    if (map.getZoom() < 1) {
      map.setZoom(1);
    }
  });

  // Fix rendering if container resizes
  setTimeout(() => map.invalidateSize(), 150);
  window.addEventListener("resize", () => map.invalidateSize());
}

// Call once when the page loads
initMap();


// ----------------- LAYERS & STATE -----------------
let aoiLayer: L.GeoJSON | null = null;
let satelliteMarker: L.Marker | null = null;
let satelliteFOVCircle: L.Circle | null = null;
let satelliteTrackingInterval: number | null = null;

let passesLayer: L.LayerGroup | null = null;

// New state for the orbit path
let orbitPathLayer: L.LayerGroup | null = null;
let isOrbitPathVisible = false;

let coverageLayer: L.GeoJSON | null = null;

// ----------------- DOM ELEMENTS -----------------
const aoiSelect = document.getElementById("aoiSelect") as HTMLSelectElement;
const tleSelect = document.getElementById("tleSelect") as HTMLSelectElement;
const aoiUpload = document.getElementById("aoiUpload") as HTMLInputElement;
const tleUpload = document.getElementById("tleUpload") as HTMLInputElement;
const uploadAoiBtn = document.getElementById("uploadAoiBtn") as HTMLButtonElement;
const uploadTleBtn = document.getElementById("uploadTleBtn") as HTMLButtonElement;
const computeBtn = document.getElementById("computePasses") as HTMLButtonElement;
const passesTableBody = document.querySelector("#passesTable tbody") as HTMLTableSectionElement;
// The single new button
const toggleOrbitPathBtn = document.getElementById("toggleOrbitPathBtn") as HTMLButtonElement;
const minElevationInput = document.getElementById("minElevation") as HTMLInputElement | null;
const daylightOnlyCheckbox = document.getElementById("daylightOnly") as HTMLInputElement | null;
const durationInput = document.getElementById("duration") as HTMLInputElement | null;

// ----------------- UTILITIES -----------------
function clearLayer(layer: L.Layer | null) { if (layer) map.removeLayer(layer); }
function clearAOI() { clearLayer(aoiLayer); aoiLayer = null; }
function clearCoverage() { clearLayer(coverageLayer); coverageLayer = null; }
function clearPasses() { clearLayer(passesLayer); passesLayer = null; }
function clearOrbit() { clearLayer(orbitPathLayer); orbitPathLayer = null; }
function enableComputeButton(enabled: boolean) { computeBtn.disabled = !enabled; }

// ----------------- FETCH TLEs / AOIs -----------------
async function fetchTLEs() {
  try {
    const res = await axios.get("http://localhost:8000/tles");
    tleSelect.innerHTML = '<option value="">-- Choose a TLE --</option>';
    res.data.forEach((tle: any) => {
      const option = document.createElement("option");
      option.value = tle.norad_id;
      option.text = tle.name;
      tleSelect.add(option);
    });
  } catch (err) { console.error(err); }
}

async function loadAOIs() {
  try {
    const res = await axios.get("http://localhost:8000/aois");
    aoiSelect.innerHTML = '<option value="">-- Choose an AOI --</option>';
    res.data.forEach((aoi: any) => {
      const option = document.createElement("option");
      option.value = aoi.id;
      option.text = aoi.name;
      aoiSelect.appendChild(option);
    });
  } catch (err) { console.error(err); }
}

// ----------------- AOI DISPLAY -----------------
async function fetchAndDisplayAOI(aoiId: number) {
  try {
    const res = await axios.get(`http://localhost:8000/aois/${aoiId}`);
    const geojson = res.data.geojson;
    clearAOI(); clearCoverage(); clearPasses();
    aoiLayer = L.geoJSON(geojson, { style: { color: "#fff", weight: 2, fillOpacity: 0.15 } }).addTo(map);
    map.fitBounds(aoiLayer.getBounds(), { padding: [20, 20] });
  } catch (err) { console.error(err); alert("Failed to load AOI"); }
}

aoiSelect.addEventListener("change", async () => {
  const id = Number(aoiSelect.value);
  if (!id) return;
  await fetchAndDisplayAOI(id);
  enableComputeButton(true);
});

// ----------------- UPLOADS -----------------
uploadAoiBtn.addEventListener("click", () => aoiUpload.click());
aoiUpload.addEventListener("change", async () => {
  const file = aoiUpload.files?.[0]; if (!file) return;
  const geojson = JSON.parse(await file.text());
  clearAOI(); clearCoverage(); clearPasses();
  aoiLayer = L.geoJSON(geojson, { style: { color: "#fff", weight: 2, fillOpacity: 0.15 } }).addTo(map);
  map.fitBounds(aoiLayer.getBounds(), { padding: [20, 20] });

  try {
    const filenameWithoutExt = file.name.replace(/\.[^/.]+$/, "");
    const res = await axios.post("http://localhost:8000/geojson", { name: filenameWithoutExt, geojson });
    await loadAOIs();
    aoiSelect.value = res.data.id;
    await fetchAndDisplayAOI(Number(res.data.id));
  } catch (err) { console.error(err); alert("AOI upload failed"); }
});

uploadTleBtn.addEventListener("click", () => tleUpload.click());
tleUpload.addEventListener("change", async () => {
  const file = tleUpload.files?.[0]; if (!file) return;
  const fd = new FormData(); fd.append("file", file);
  try {
    await axios.post("http://localhost:8000/tle/upload", fd, { headers: { "Content-Type": "multipart/form-data" } });
    await fetchTLEs();
    alert("TLE uploaded");
  } catch (err) { console.error(err); alert("TLE upload failed"); }
});

// ----------------- SATELLITE TRACKING -----------------
async function updateSatellite(tleId: number) {
  try {
    const res = await axios.get("http://localhost:8000/track", { params: { tle_noradid: tleId } });
    const { latitude, longitude, fov_radius_m } = res.data;

    if (satelliteMarker) map.removeLayer(satelliteMarker);
    if (satelliteFOVCircle) map.removeLayer(satelliteFOVCircle);

    satelliteMarker = L.marker([latitude, longitude], { icon: L.divIcon({ className: 'satellite-marker', html: '🛰️', iconSize: [24, 24] }) }).addTo(map);
    satelliteFOVCircle = L.circle([latitude, longitude], { radius: fov_radius_m, color: "#2d7dff", fillOpacity: 0.15, weight: 2 }).addTo(map);

  } catch (err) { console.error("Error updating satellite", err); }
}

tleSelect.addEventListener("change", () => {
  const tleId = Number(tleSelect.value);
  if (!tleId) return;
  if (satelliteTrackingInterval) clearInterval(satelliteTrackingInterval);

  updateSatellite(tleId);
  satelliteTrackingInterval = window.setInterval(() => updateSatellite(tleId), 5000);
});

// ----------------- COMPUTE PASSES -----------------
computeBtn.addEventListener("click", async () => {
  const tleId = Number(tleSelect.value);
  const aoiId = Number(aoiSelect.value);
  if (!tleId || !aoiId) { alert("Select TLE and AOI"); return; }

  const minElevation = minElevationInput ? Number(minElevationInput.value) : 5;
  const daylightOnly = daylightOnlyCheckbox ? daylightOnlyCheckbox.checked : true;
  const duration = durationInput ? Number(durationInput.value) || 24 : 24;

  clearPasses(); clearCoverage();

  try {
    const res = await axios.post("http://localhost:8000/passes", {
      tle_noradid: tleId,
      aoi_id: aoiId,
      min_elevation: minElevation,
      daylight_only: daylightOnly,
      duration: duration
    });

    const passes = res.data;
    passesTableBody.innerHTML = "";
    passesLayer = L.layerGroup().addTo(map);

    passes.forEach((p: any) => {
      const latlngs = p.track_coords.map((c: number[]) => [c[1], c[0]]);
      L.polyline(latlngs, { color: "#ff5577", weight: 3 }).addTo(passesLayer);

      const row = passesTableBody.insertRow();
      row.insertCell().innerText = new Date(p.start_time).toLocaleString();
      row.insertCell().innerText = new Date(p.end_time).toLocaleString();
      row.insertCell().innerText = (p.max_elevation ?? 0).toFixed(1);
    });

    if (passesLayer && (passesLayer as any).getBounds && (passesLayer as any).getLayers().length > 0) {
      const bounds = (passesLayer as any).getBounds();
      map.fitBounds(bounds, { padding: [20, 20] });
    }
  } catch (err) {
    console.error("Error computing passes", err);
    alert("Error computing passes. See console.");
  }
});

// ----------------- ORBITAL PATH TOGGLE -----------------
async function toggleOrbitalPath(tleId: number) {
  if (isOrbitPathVisible) {
    // If visible, hide it
    clearLayer(orbitPathLayer);
    orbitPathLayer = null;
    isOrbitPathVisible = false;
    toggleOrbitPathBtn.textContent = "Show Orbital Path";
  } else {
    // If hidden, show it
    try {
      const res = await axios.get(`http://localhost:8000/OrbitalPath/${tleId}`);
      const latlngs = res.data.map((c: number[]) => [c[1], c[0]]);

      orbitPathLayer = L.layerGroup().addTo(map);
      L.polyline(latlngs, { color: "#00ff88", weight: 6, opacity: 0.3 }).addTo(orbitPathLayer);
      L.polyline(latlngs, { color: "#00ff88", weight: 2, opacity: 1 }).addTo(orbitPathLayer);

      isOrbitPathVisible = true;
      toggleOrbitPathBtn.textContent = "Hide Orbital Path";

      if ((orbitPathLayer as any).getBounds) {
        const bounds = (orbitPathLayer as any).getBounds();
        map.fitBounds(bounds, { padding: [20, 20] });
      }

    } catch (err) {
      console.error("Error computing orbital path", err);
      alert("Error computing orbital path. See console.");
    }
  }
}

// ----------------- BUTTON EVENTS -----------------
// The single event listener for the new toggle button
toggleOrbitPathBtn.addEventListener("click", () => {
  const tleId = Number(tleSelect.value);
  if (!tleId) {
    alert("Select a TLE first!");
    return;
  }
  toggleOrbitalPath(tleId);
});

// ----------------- INITIAL LOAD -----------------
fetchTLEs();
loadAOIs();
// Add this at the very end of your main.ts file
setTimeout(function(){ map.invalidateSize()}, 400);