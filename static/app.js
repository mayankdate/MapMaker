// Personal Map Studio frontend
// State is intentionally kept in module-level objects; single-user local app.

const LAYER_NAMES = ['water', 'parks', 'buildings', 'rail', 'minor', 'major', 'paths'];
const DEFAULT_LINEWIDTHS = { rail: 0.46, minor: 0.42, major: 1.02, paths: 0.23 };
const DEFAULT_LAYER_VISIBILITY = {
  water: true, parks: true, buildings: false,
  rail: true, minor: true, major: true, paths: true,
};

const CROSS_SVG = `<svg viewBox="0 0 24 24" class="cross-svg" fill="currentColor" xmlns="http://www.w3.org/2000/svg">
  <rect x="4" y="10" width="16" height="4" rx="0.5"/>
  <rect x="10" y="4" width="4" height="16" rx="0.5"/>
</svg>`;

const state = {
  bbox: null,           // [south, west, north, east]
  markers: [],          // [{id, lat, lon, label, icon}]
  nextMarkerId: 1,
  icons: { defaults: [], user: [] },
  selectedIcon: null,   // null == cross, else filename
  layerVisibility: { ...DEFAULT_LAYER_VISIBILITY },
  layerWidths: { ...DEFAULT_LINEWIDTHS },
  layerColors: {},      // pulled from #color-grid on preview/export
  clickAddsMarker: false,
  fetchDone: false,
};

const leafletMarkers = new Map(); // id -> L.Marker

// ---------- Leaflet setup ----------
const map = L.map('map', { zoomControl: true }).setView([19.076, 72.8777], 12);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
  attribution: '© OpenStreetMap contributors',
  maxZoom: 19,
}).addTo(map);

const bboxLayer = L.featureGroup().addTo(map);
let bboxRect = null;

const drawControl = new L.Control.Draw({
  draw: {
    rectangle: { shapeOptions: { color: '#e1ad69', weight: 2 } },
    polyline: false, polygon: false, circle: false, circlemarker: false, marker: false,
  },
  edit: { featureGroup: bboxLayer, remove: false, edit: false },
});
map.addControl(drawControl);

map.on(L.Draw.Event.CREATED, (event) => {
  const layer = event.layer;
  bboxLayer.clearLayers();
  bboxLayer.addLayer(layer);
  const b = layer.getBounds();
  state.bbox = [b.getSouth(), b.getWest(), b.getNorth(), b.getEast()];
  updateBboxStatus();
});

map.on('click', (event) => {
  if (!state.clickAddsMarker) return;
  addMarker({
    lat: event.latlng.lat,
    lon: event.latlng.lng,
    label: '',
    icon: state.selectedIcon,
  });
});

function updateBboxStatus() {
  const s = document.getElementById('bbox-status');
  if (!state.bbox) {
    s.textContent = 'Draw a rectangle with the ▢ tool to select your print area.';
    updateDimensionsHint();
    return;
  }
  const [south, west, north, east] = state.bbox;
  const heightKm = (north - south) * 111.2;
  const midLat = (south + north) / 2;
  const widthKm = (east - west) * 111.2 * Math.cos(midLat * Math.PI / 180);
  s.innerHTML = `Selected area: <strong>${widthKm.toFixed(1)} × ${heightKm.toFixed(1)} km</strong>. Ready to fetch.`;
  updateDimensionsHint();
}

function updateDimensionsHint() {
  const hint = document.getElementById('dimensions-hint');
  if (!state.bbox) {
    hint.textContent = 'Draw a rectangle to see final dimensions.';
    return;
  }
  const longSide = parseFloat(document.getElementById('long-side-in').value);
  if (!Number.isFinite(longSide) || longSide <= 0) {
    hint.textContent = 'Enter a valid long-edge length.';
    return;
  }
  const [south, west, north, east] = state.bbox;
  const heightKm = (north - south) * 111.2;
  const midLat = (south + north) / 2;
  const widthKm = (east - west) * 111.2 * Math.cos(midLat * Math.PI / 180);
  const isLandscape = widthKm >= heightKm;
  const shortSide = isLandscape
    ? longSide * heightKm / widthKm
    : longSide * widthKm / heightKm;
  const width = isLandscape ? longSide : shortSide;
  const height = isLandscape ? shortSide : longSide;
  hint.innerHTML = `Final print: <strong>${width.toFixed(2)} × ${height.toFixed(2)} in</strong> (${isLandscape ? 'landscape' : 'portrait'}).`;
}

// ---------- Search (Nominatim via backend) ----------
const searchInput = document.getElementById('search-input');
const searchButton = document.getElementById('search-button');
const searchResults = document.getElementById('search-results');

async function runSearch() {
  const q = searchInput.value.trim();
  if (!q) return;
  searchResults.innerHTML = '<div class="result"><div class="label">Searching…</div></div>';
  searchResults.classList.remove('hidden');
  const response = await fetch(`/api/geocode?q=${encodeURIComponent(q)}`);
  if (!response.ok) {
    searchResults.innerHTML = `<div class="result"><div class="label">Search failed: ${response.status}</div></div>`;
    return;
  }
  const data = await response.json();
  if (!data.results.length) {
    searchResults.innerHTML = '<div class="result"><div class="label">No results.</div></div>';
    return;
  }
  searchResults.innerHTML = '';
  for (const item of data.results) {
    const row = document.createElement('div');
    row.className = 'result';
    const label = document.createElement('div');
    label.className = 'label';
    label.textContent = item.label;
    label.addEventListener('click', () => jumpTo(item));
    const jumpBtn = document.createElement('button');
    jumpBtn.textContent = 'Go';
    jumpBtn.addEventListener('click', () => jumpTo(item));
    const markerBtn = document.createElement('button');
    markerBtn.textContent = '+ Marker';
    markerBtn.className = 'primary';
    markerBtn.style.width = 'auto';
    markerBtn.style.marginBottom = '0';
    markerBtn.addEventListener('click', () => {
      addMarker({ lat: item.lat, lon: item.lon, label: item.label.split(',')[0], icon: state.selectedIcon });
      searchResults.classList.add('hidden');
    });
    row.appendChild(label);
    row.appendChild(jumpBtn);
    row.appendChild(markerBtn);
    searchResults.appendChild(row);
  }
}

function jumpTo(item) {
  if (item.bbox) {
    const [south, north, west, east] = item.bbox;
    map.fitBounds([[south, west], [north, east]]);
  } else {
    map.setView([item.lat, item.lon], 14);
  }
  searchResults.classList.add('hidden');
}

searchButton.addEventListener('click', runSearch);
searchInput.addEventListener('keydown', (e) => { if (e.key === 'Enter') runSearch(); });
document.addEventListener('click', (e) => {
  if (!e.target.closest('.search') && !e.target.closest('.search-results')) {
    searchResults.classList.add('hidden');
  }
});

// ---------- Icons ----------
async function loadIcons() {
  const response = await fetch('/api/icons');
  const data = await response.json();
  state.icons = data;
  renderIconChoices();
  updateAllMarkerIconSelectors();
}

function renderIconChoices() {
  const container = document.getElementById('icon-choices');
  container.innerHTML = '';

  const crossBtn = document.createElement('button');
  crossBtn.className = 'icon-choice';
  crossBtn.title = 'Gold cross (drawn)';
  crossBtn.innerHTML = CROSS_SVG;
  crossBtn.dataset.value = '';
  container.appendChild(crossBtn);

  for (const group of ['defaults', 'user']) {
    for (const icon of state.icons[group]) {
      const btn = document.createElement('button');
      btn.className = 'icon-choice';
      btn.title = icon.name;
      btn.dataset.value = icon.name;
      const img = document.createElement('img');
      img.src = icon.url;
      img.alt = icon.name;
      btn.appendChild(img);
      container.appendChild(btn);
    }
  }

  container.querySelectorAll('.icon-choice').forEach((btn) => {
    btn.addEventListener('click', () => {
      state.selectedIcon = btn.dataset.value || null;
      container.querySelectorAll('.icon-choice').forEach((b) => b.classList.remove('selected'));
      btn.classList.add('selected');
    });
  });
  const wanted = state.selectedIcon || '';
  const match = container.querySelector(`.icon-choice[data-value="${wanted}"]`);
  if (match) match.classList.add('selected');
  else container.querySelector('.icon-choice').classList.add('selected');
}

function iconUrl(name) {
  if (!name) return null;
  const inDefaults = state.icons.defaults.find((i) => i.name === name);
  if (inDefaults) return inDefaults.url;
  const inUser = state.icons.user.find((i) => i.name === name);
  if (inUser) return inUser.url;
  return null;
}

// ---------- Markers ----------
function addMarker({ lat, lon, label, icon }) {
  const id = state.nextMarkerId++;
  const marker = { id, lat, lon, label: label || '', icon: icon || null };
  state.markers.push(marker);
  const leafletMarker = buildLeafletMarker(marker);
  leafletMarkers.set(id, leafletMarker);
  leafletMarker.addTo(map);
  renderMarkerList();
}

function buildLeafletMarker(marker) {
  const url = iconUrl(marker.icon);
  const options = { draggable: true, title: marker.label };
  if (url) {
    options.icon = L.icon({ iconUrl: url, iconSize: [30, 30], iconAnchor: [15, 15] });
  } else {
    options.icon = L.divIcon({
      className: 'cross-marker',
      html: `<div style="color:#e1ad69;font-size:22px;line-height:22px;font-weight:900;text-shadow:0 0 3px rgba(0,0,0,0.7);transform:translate(-50%,-50%);position:absolute;">+</div>`,
      iconSize: [22, 22],
      iconAnchor: [0, 0],
    });
  }
  const leafletMarker = L.marker([marker.lat, marker.lon], options);
  leafletMarker.on('dragend', () => {
    const pos = leafletMarker.getLatLng();
    marker.lat = pos.lat;
    marker.lon = pos.lng;
    renderMarkerList();
  });
  return leafletMarker;
}

function refreshLeafletMarker(marker) {
  const existing = leafletMarkers.get(marker.id);
  if (existing) map.removeLayer(existing);
  const next = buildLeafletMarker(marker);
  next.addTo(map);
  leafletMarkers.set(marker.id, next);
}

function removeMarker(id) {
  const existing = leafletMarkers.get(id);
  if (existing) map.removeLayer(existing);
  leafletMarkers.delete(id);
  state.markers = state.markers.filter((m) => m.id !== id);
  renderMarkerList();
}

function renderMarkerList() {
  const list = document.getElementById('marker-list');
  list.innerHTML = '';
  if (!state.markers.length) {
    const li = document.createElement('li');
    li.style.textAlign = 'center';
    li.style.color = 'var(--muted)';
    li.style.fontSize = '12px';
    li.style.background = 'transparent';
    li.style.border = '1px dashed var(--border)';
    li.textContent = 'No markers yet. Search a place, click the map, or enter coordinates.';
    list.appendChild(li);
    return;
  }
  for (const marker of state.markers) {
    const li = document.createElement('li');

    const iconCell = document.createElement('div');
    iconCell.className = 'icon-cell';
    const url = iconUrl(marker.icon);
    if (url) {
      const img = document.createElement('img');
      img.src = url;
      iconCell.appendChild(img);
    } else {
      iconCell.innerHTML = CROSS_SVG;
      iconCell.querySelector('svg').style.width = '20px';
      iconCell.querySelector('svg').style.height = '20px';
    }
    li.appendChild(iconCell);

    const info = document.createElement('div');
    info.className = 'info';

    const labelInput = document.createElement('input');
    labelInput.type = 'text';
    labelInput.placeholder = 'Label (optional)';
    labelInput.value = marker.label;
    labelInput.addEventListener('input', () => { marker.label = labelInput.value; });
    info.appendChild(labelInput);

    const coords = document.createElement('div');
    coords.className = 'coords';
    const latInput = document.createElement('input');
    latInput.type = 'number';
    latInput.step = '0.000001';
    latInput.value = marker.lat.toFixed(6);
    const lonInput = document.createElement('input');
    lonInput.type = 'number';
    lonInput.step = '0.000001';
    lonInput.value = marker.lon.toFixed(6);
    const applyCoords = () => {
      const nextLat = parseFloat(latInput.value);
      const nextLon = parseFloat(lonInput.value);
      if (Number.isFinite(nextLat) && Number.isFinite(nextLon)) {
        marker.lat = nextLat;
        marker.lon = nextLon;
        const lm = leafletMarkers.get(marker.id);
        if (lm) lm.setLatLng([nextLat, nextLon]);
      }
    };
    latInput.addEventListener('change', applyCoords);
    lonInput.addEventListener('change', applyCoords);
    coords.appendChild(latInput);
    coords.appendChild(lonInput);
    info.appendChild(coords);

    const iconSelect = document.createElement('select');
    iconSelect.className = 'icon-select';
    const crossOpt = document.createElement('option');
    crossOpt.value = '';
    crossOpt.textContent = 'Gold cross (drawn)';
    iconSelect.appendChild(crossOpt);
    for (const group of ['defaults', 'user']) {
      const groupLabel = document.createElement('optgroup');
      groupLabel.label = group === 'defaults' ? 'Built-in' : 'markers/';
      for (const icon of state.icons[group]) {
        const opt = document.createElement('option');
        opt.value = icon.name;
        opt.textContent = icon.name;
        groupLabel.appendChild(opt);
      }
      if (groupLabel.children.length) iconSelect.appendChild(groupLabel);
    }
    iconSelect.value = marker.icon || '';
    iconSelect.addEventListener('change', () => {
      marker.icon = iconSelect.value || null;
      refreshLeafletMarker(marker);
      renderMarkerList();
    });
    info.appendChild(iconSelect);
    li.appendChild(info);

    const actions = document.createElement('div');
    actions.className = 'actions';
    const focusBtn = document.createElement('button');
    focusBtn.textContent = 'Focus';
    focusBtn.addEventListener('click', () => map.setView([marker.lat, marker.lon], 15));
    const deleteBtn = document.createElement('button');
    deleteBtn.textContent = 'Delete';
    deleteBtn.addEventListener('click', () => removeMarker(marker.id));
    actions.appendChild(focusBtn);
    actions.appendChild(deleteBtn);
    li.appendChild(actions);

    list.appendChild(li);
  }
}

function updateAllMarkerIconSelectors() {
  renderMarkerList();
}

// ---------- Marker add buttons ----------
document.getElementById('add-marker-here').addEventListener('click', () => {
  const c = map.getCenter();
  addMarker({ lat: c.lat, lon: c.lng, label: '', icon: state.selectedIcon });
});

document.getElementById('marker-click-mode').addEventListener('change', (e) => {
  state.clickAddsMarker = e.target.checked;
  map.getContainer().style.cursor = state.clickAddsMarker ? 'crosshair' : '';
});

const coordModal = document.getElementById('coord-modal');
document.getElementById('add-marker-coords').addEventListener('click', () => {
  document.getElementById('coord-lat').value = '';
  document.getElementById('coord-lon').value = '';
  document.getElementById('coord-label').value = '';
  coordModal.classList.remove('hidden');
});
document.getElementById('coord-cancel').addEventListener('click', () => coordModal.classList.add('hidden'));
document.getElementById('coord-add').addEventListener('click', () => {
  const lat = parseFloat(document.getElementById('coord-lat').value);
  const lon = parseFloat(document.getElementById('coord-lon').value);
  if (!Number.isFinite(lat) || !Number.isFinite(lon)) {
    alert('Enter numeric latitude and longitude.');
    return;
  }
  const label = document.getElementById('coord-label').value.trim();
  addMarker({ lat, lon, label, icon: state.selectedIcon });
  coordModal.classList.add('hidden');
});

// ---------- Layer controls ----------
function buildLayerControls() {
  const container = document.getElementById('layer-controls');
  container.innerHTML = '';
  for (const name of LAYER_NAMES) {
    const row = document.createElement('div');
    row.className = 'layer-row';

    const check = document.createElement('input');
    check.type = 'checkbox';
    check.checked = state.layerVisibility[name];
    check.addEventListener('change', () => { state.layerVisibility[name] = check.checked; });
    row.appendChild(check);

    const label = document.createElement('div');
    label.className = 'layer-name';
    label.textContent = name;
    row.appendChild(label);

    if (name in DEFAULT_LINEWIDTHS) {
      const widthLabel = document.createElement('span');
      widthLabel.style.fontSize = '11px';
      widthLabel.style.color = 'var(--muted)';
      widthLabel.textContent = state.layerWidths[name].toFixed(2);
      const range = document.createElement('input');
      range.type = 'range';
      range.min = '0.1';
      range.max = '3';
      range.step = '0.05';
      range.value = state.layerWidths[name];
      range.title = 'Line width';
      range.addEventListener('input', () => {
        state.layerWidths[name] = parseFloat(range.value);
        widthLabel.textContent = state.layerWidths[name].toFixed(2);
      });
      row.appendChild(range);
      row.appendChild(widthLabel);
    } else {
      row.appendChild(document.createElement('span'));
      row.appendChild(document.createElement('span'));
    }
    container.appendChild(row);
  }
}

// ---------- Fetch + preview + export ----------
document.getElementById('fetch-button').addEventListener('click', async () => {
  if (!state.bbox) {
    setStatus('fetch-status', 'Draw a rectangle first.', 'error');
    return;
  }
  const includeBuildings = document.getElementById('include-buildings').checked;
  setStatus('fetch-status', 'Fetching from OpenStreetMap… (first request can take a minute)');
  const response = await fetch('/api/fetch', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ bbox: state.bbox, include_buildings: includeBuildings }),
  });
  if (!response.ok) {
    const text = await response.text();
    setStatus('fetch-status', `Fetch failed: ${text}`, 'error');
    return;
  }
  const data = await response.json();
  state.fetchDone = true;
  const parts = LAYER_NAMES.map((n) => `${n}: ${data.counts[n]}`).join(' · ');
  setStatus('fetch-status',
    `Fetched ${data.size_km.width}×${data.size_km.height} km — ${parts}`, 'success');
});

function collectPayload(includeFormats = false) {
  const style = {};
  document.querySelectorAll('.color-grid input[type="color"]').forEach((input) => {
    style[input.dataset.style] = input.value;
  });
  for (const name of LAYER_NAMES) {
    style[`show_${name}`] = state.layerVisibility[name];
    if (name in DEFAULT_LINEWIDTHS) style[`width_${name}`] = state.layerWidths[name];
  }
  style.show_attribution = document.getElementById('show-attribution').checked;
  style.show_place_labels = document.getElementById('show-place-labels').checked;
  document.querySelectorAll('[data-place-tier]').forEach((input) => {
    style[`show_places_${input.dataset.placeTier}`] = input.checked;
  });
  style.show_road_labels = document.getElementById('show-road-labels').checked;
  style.show_road_labels_major = document.getElementById('show-road-labels-major').checked;
  style.show_road_labels_minor = document.getElementById('show-road-labels-minor').checked;

  const markers = state.markers.map((m) => ({
    lat: m.lat, lon: m.lon, label: m.label, icon: m.icon,
  }));
  const payload = {
    style,
    markers,
    title: document.getElementById('title-input').value,
    title_placement: document.getElementById('title-placement').value,
    long_side_in: parseFloat(document.getElementById('long-side-in').value),
    marker_size: parseFloat(document.getElementById('marker-size').value),
  };
  if (includeFormats) {
    payload.formats = Array.from(
      document.querySelectorAll('.export-formats input[type="checkbox"]:checked')
    ).map((cb) => cb.value);
  }
  return payload;
}

document.getElementById('preview-button').addEventListener('click', async () => {
  if (!state.fetchDone) {
    setStatus('preview-status', 'Fetch features before previewing.', 'error');
    return;
  }
  setStatus('preview-status', 'Rendering preview…');
  const response = await fetch('/api/preview', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(collectPayload()),
  });
  if (!response.ok) {
    const text = await response.text();
    setStatus('preview-status', `Preview failed: ${text}`, 'error');
    return;
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const img = document.getElementById('preview-image');
  img.onload = () => URL.revokeObjectURL(url);
  img.src = url;
  document.getElementById('preview-wrap').classList.remove('hidden');
  setStatus('preview-status', 'Preview updated.', 'success');
});

document.getElementById('export-button').addEventListener('click', async () => {
  if (!state.fetchDone) {
    setStatus('export-status', 'Fetch features before exporting.', 'error');
    return;
  }
  const payload = collectPayload(true);
  if (!payload.formats.length) {
    setStatus('export-status', 'Tick at least one export format.', 'error');
    return;
  }
  setStatus('export-status', `Exporting ${payload.formats.length} format(s)…`);
  const response = await fetch('/api/export', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const text = await response.text();
    setStatus('export-status', `Export failed: ${text}`, 'error');
    return;
  }
  const data = await response.json();
  const [w, h] = data.page_inches;
  setStatus('export-status',
    `Exported ${data.files.length} files (${w} × ${h} in) to ${data.export_dir}/`, 'success');
});

document.getElementById('long-side-in').addEventListener('input', updateDimensionsHint);

document.getElementById('marker-size').addEventListener('input', (e) => {
  document.getElementById('marker-size-label').textContent = e.target.value;
});

// ---------- Utilities ----------
function setStatus(elementId, message, kind) {
  const el = document.getElementById(elementId);
  el.textContent = message;
  el.className = 'status' + (kind ? ' ' + kind : '');
}

// ---------- Init ----------
buildLayerControls();
renderMarkerList();
loadIcons();
