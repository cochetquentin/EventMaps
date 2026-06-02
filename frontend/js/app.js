/* global L */
import { setMap, setClusterGroup, deactivatedPills, setShowOnlyFavorites, showOnlyFavorites, markerMap, allEvents } from './state.js';
import { isoDate, todayJST, computePresets } from './utils.js';
import { toggleFavorite, isFavorite, getIcon, updateFavPill } from './favorites.js';
import { buildPopup } from './popups.js';
import { renderMarkers } from './markers.js';
import { buildPills } from './filters.js';
import {
  fetchEventsByBbox,
  setBboxFetchEnabled,
  bboxFetchEnabled,
  fetchDebounceTimer,
  setFetchDebounceTimer,
} from './api.js';
import { setupGeolocation } from './geolocation.js';

// ── Map init ──────────────────────────────────────────────────────────────
const map = L.map('map').setView([35.68, 139.69], 11);
L.tileLayer('https://tiles.stadiamaps.com/tiles/alidade_smooth/{z}/{x}/{y}{r}.png', {
  maxZoom: 20,
  attribution: '© <a href="https://stadiamaps.com/">Stadia Maps</a> © <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
}).addTo(map);
setMap(map);

const clusterGroup = L.markerClusterGroup({ chunkedLoading: true, maxClusterRadius: 50 });
map.addLayer(clusterGroup);
setClusterGroup(clusterGroup);

// ── Debounced bbox fetch on map move ──────────────────────────────────────
// bboxFetchEnabled is a live binding — false until initial load succeeds
map.on('moveend', () => {
  if (!bboxFetchEnabled) return;
  clearTimeout(fetchDebounceTimer);
  setFetchDebounceTimer(setTimeout(fetchEventsByBbox, 300));
});

// ── Popup fav button ──────────────────────────────────────────────────────
function attachFavHandler(btn) {
  btn.addEventListener('click', () => {
    const id = btn.dataset.favId;
    toggleFavorite(id);
    const fav = isFavorite(id);
    btn.textContent = fav ? '★' : '☆';
    btn.classList.toggle('active', fav);
    const marker = markerMap.get(id);
    if (marker) {
      const ev = allEvents.find(ev => ev.id === id);
      if (ev) {
        marker.setIcon(getIcon(ev, fav));
        marker.setPopupContent(buildPopup(ev));
        // Popup is still open — re-attach handler to the freshly built button
        if (marker.isPopupOpen()) {
          const newBtn = marker.getPopup().getElement().querySelector('[data-fav-id]');
          if (newBtn) attachFavHandler(newBtn);
        }
      }
    }
    updateFavPill();
    if (showOnlyFavorites && !fav) renderMarkers();
  });
}

map.on('popupopen', (e) => {
  const btn = e.popup.getElement().querySelector('[data-fav-id]');
  if (btn) attachFavHandler(btn);
});

// events-list.js dispatches this after setPopupContent when popup is open
document.addEventListener('popup-fav-rebind', (e) => {
  const btn = e.detail.marker.getPopup().getElement().querySelector('[data-fav-id]');
  if (btn) attachFavHandler(btn);
});

// ── Date presets ──────────────────────────────────────────────────────────
const PRESETS = computePresets();

function applyPreset(name) {
  const [from, to] = PRESETS[name];
  document.getElementById('filter-date-from').value = from;
  document.getElementById('filter-date-to').value   = to;
  document.querySelectorAll('.preset-btn').forEach(b => b.classList.toggle('active', b.dataset.preset === name));
  clearTimeout(fetchDebounceTimer);
  setFetchDebounceTimer(setTimeout(fetchEventsByBbox, 300));
}

document.querySelectorAll('.preset-btn[data-preset]').forEach(btn => {
  btn.addEventListener('click', () => applyPreset(btn.dataset.preset));
});

// ── Date inputs ───────────────────────────────────────────────────────────
document.getElementById('filter-date-from').addEventListener('change', () => {
  document.querySelectorAll('.preset-btn').forEach(b => b.classList.remove('active'));
  clearTimeout(fetchDebounceTimer);
  setFetchDebounceTimer(setTimeout(fetchEventsByBbox, 300));
});

document.getElementById('filter-date-to').addEventListener('change', () => {
  document.querySelectorAll('.preset-btn').forEach(b => b.classList.remove('active'));
  renderMarkers();
});

document.getElementById('date-custom-btn').addEventListener('click', () => {
  document.getElementById('date-dropdown').classList.toggle('hidden');
});

// ── Reset ─────────────────────────────────────────────────────────────────
document.getElementById('reset-filters').addEventListener('click', () => {
  document.getElementById('filter-date-from').value = isoDate(todayJST());
  document.getElementById('filter-date-to').value   = '';
  document.getElementById('search-input').value     = '';
  deactivatedPills.clear();
  setShowOnlyFavorites(false);
  document.querySelectorAll('.pill').forEach(p => {
    if (p.classList.contains('fav-pill')) p.classList.remove('active');
    else p.classList.add('active');
  });
  document.querySelectorAll('.preset-btn').forEach(b => b.classList.remove('active'));
  document.getElementById('date-dropdown').classList.add('hidden');
  clearTimeout(fetchDebounceTimer);
  setFetchDebounceTimer(setTimeout(fetchEventsByBbox, 300));
});

// ── Search ────────────────────────────────────────────────────────────────
document.getElementById('search-input').addEventListener('input', renderMarkers);

// ── Scrape ────────────────────────────────────────────────────────────────
const scrapeBtn = document.getElementById('scrape-btn');
let pollInterval = null;

async function startScrape() {
  scrapeBtn.classList.add('running');
  await fetch('/scrape', { method: 'POST' });
  pollInterval = setInterval(async () => {
    const res  = await fetch('/scrape/status');
    const data = await res.json();
    if (data.status !== 'running') {
      clearInterval(pollInterval);
      scrapeBtn.classList.remove('running');
      await loadEvents();
    }
  }, 2000);
}

scrapeBtn.addEventListener('click', startScrape);

// ── Geolocation ───────────────────────────────────────────────────────────
setupGeolocation();

// ── Init ──────────────────────────────────────────────────────────────────
async function loadEvents() {
  document.getElementById('filter-date-from').value = isoDate(todayJST());
  try {
    await fetchEventsByBbox();
    setBboxFetchEnabled(true);
  } catch (e) {
    document.getElementById('stats').textContent = 'Erreur de chargement.';
    console.error(e);
  }
}

loadEvents();
