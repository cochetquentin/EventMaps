/* global L */
import { setMap, setClusterGroup, deactivatedPills, setShowOnlyFavorites, showOnlyFavorites, markerMap, allEvents, setUserPosition, setProximityMode, showAllEvents, setShowAllEvents } from './state.js';
import { isoDate, todayJST, computePresets } from './utils.js';
import { toggleFavorite, isFavorite, getIcon, updateFavPill } from './favorites.js';
import { buildPopup } from './popups.js';
import { renderMarkers } from './markers.js';
import { buildPills, toggleAllCategoryPills } from './filters.js';
import {
  fetchEventsByBbox,
  setBboxFetchEnabled,
  bboxFetchEnabled,
  fetchDebounceTimer,
  setFetchDebounceTimer,
} from './api.js';
import { setupGeolocation, cancelGeolocation } from './geolocation.js';
import { initDrawer, openDrawer } from './drawer.js';
import { updateURL, restoreFromURL } from './share.js';
import { initMobileUI } from './mobile-ui.js';
import { initTokyoLive } from './tokyo-live.js';

// ── Map init ──────────────────────────────────────────────────────────────
const map = L.map('map').setView([35.68, 139.69], 11);
L.tileLayer('https://tiles.stadiamaps.com/tiles/alidade_smooth/{z}/{x}/{y}{r}.png', {
  maxZoom: 20,
  attribution: '© <a href="https://stadiamaps.com/">Stadia Maps</a> © <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
}).addTo(map);
setMap(map);

const clusterGroup = L.markerClusterGroup({
  chunkedLoading: true,
  maxClusterRadius: 50,
  // Ne pas zoomer au clic sur un amas : des événements co-localisés (même lieu,
  // plusieurs dates) ne se séparent jamais par le zoom, ce qui zoomait à l'infini
  // cran par cran. On les étale sur place (spiderfy) à la place — voir clusterclick.
  // spiderfyOnMaxZoom off : sinon markercluster déclenche aussi son propre spiderfy
  // au zoom max, en doublon de notre handler.
  zoomToBoundsOnClick: false,
  spiderfyOnMaxZoom: false,
});
map.addLayer(clusterGroup);
setClusterGroup(clusterGroup);
clusterGroup.on('clusterclick', (e) => e.layer.spiderfy());
initDrawer();

// ── Debounced bbox fetch on map move ──────────────────────────────────────
// bboxFetchEnabled is a live binding — false until initial load succeeds
// L'autoPan d'une bulle émet aussi un moveend : on le saute pour ne pas
// reconstruire tous les marqueurs (ce qui fermerait la bulle) alors que la zone
// visible n'a pas réellement changé. autopanstart précède ce moveend-là.
let skipFetchOnce = false;
map.on('autopanstart', () => { skipFetchOnce = true; });
map.on('moveend', () => {
  if (!bboxFetchEnabled) return;
  // En mode « Tous », la liste ne dépend pas de la zone visible : inutile de recharger.
  if (showAllEvents) return;
  if (skipFetchOnce) { skipFetchOnce = false; return; }
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

// ── Popup « Plus d'infos » → drawer ────────────────────────────────────────
// Écoute déléguée : survit au re-render du popup lors d'un toggle favori.
document.addEventListener('click', (e) => {
  const btn = e.target.closest('.pop-info-btn');
  if (!btn) return;
  const ev = allEvents.find(ev => ev.id === btn.dataset.infoId);
  if (ev) {
    map.closePopup();
    openDrawer(ev);
  }
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
  clearTimeout(fetchDebounceTimer);
  setFetchDebounceTimer(setTimeout(fetchEventsByBbox, 300));
});

// ── Reset ─────────────────────────────────────────────────────────────────
document.getElementById('reset-filters').addEventListener('click', () => {
  document.getElementById('filter-date-from').value = isoDate(todayJST());
  document.getElementById('filter-date-to').value   = '';
  document.getElementById('search-input').value     = '';
  deactivatedPills.clear();
  setShowOnlyFavorites(false);
  cancelGeolocation();
  setProximityMode(false);
  setUserPosition(null);
  const locBtn = document.getElementById('locate-btn');
  locBtn.classList.remove('active', 'loading');
  locBtn.disabled = false;
  document.querySelectorAll('.pill').forEach(p => {
    if (p.classList.contains('fav-pill')) p.classList.remove('active');
    else p.classList.add('active');
  });
  document.querySelectorAll('.preset-btn').forEach(b => b.classList.remove('active'));
  updateURL();
  clearTimeout(fetchDebounceTimer);
  setFetchDebounceTimer(setTimeout(fetchEventsByBbox, 300));
});

// ── Search ────────────────────────────────────────────────────────────────
let searchDebounceTimer = null;
document.getElementById('search-input').addEventListener('input', () => {
  clearTimeout(searchDebounceTimer);
  // fetchEventsByBbox lit le champ search directement depuis le DOM
  searchDebounceTimer = setTimeout(fetchEventsByBbox, 300);
});

// ── Scrape ────────────────────────────────────────────────────────────────
const scrapeBtn = document.getElementById('scrape-btn');
let pollInterval = null;

async function startScrape() {
  scrapeBtn.classList.add('running');
  const res = await fetch('/scrape', { method: 'POST' });
  if (res.status === 403) {
    scrapeBtn.classList.remove('running');
    scrapeBtn.title = 'Scraping non autorisé (token requis)';
    return;
  }
  const data = await res.json();
  // Si un scrape est déjà en cours, poller le status global pour recharger les events à la fin
  const statusUrl = data.status === 'already_running' || data.job_id == null
    ? '/scrape/status'
    : `/scrape/status?job_id=${data.job_id}`;
  pollInterval = setInterval(async () => {
    const statusRes = await fetch(statusUrl);
    const statusData = await statusRes.json();
    if (statusData.status !== 'running') {
      clearInterval(pollInterval);
      scrapeBtn.classList.remove('running');
      await loadEvents();
    }
  }, 2000);
}

async function initScrapeButton() {
  try {
    const res = await fetch('/scrape/config');
    const cfg = await res.json();
    if (!cfg.public) {
      scrapeBtn.style.display = 'none';
    }
  } catch {
    // si /scrape/config échoue, on laisse le bouton visible (mode dégradé)
  }
  scrapeBtn.addEventListener('click', startScrape);
}

initScrapeButton();

// ── Geolocation ───────────────────────────────────────────────────────────
setupGeolocation();

// ── UI mobile (bottom-sheet + en-tête repliable) ──────────────────────────
initMobileUI();

// ── Context Cards (en-tête desktop) ───────────────────────────────────────
initTokyoLive();

// ── Portée de la liste : zone visible vs tous les événements filtrés ───────
const scopeToggle = document.getElementById('scope-toggle');
function updateScopeToggle() {
  scopeToggle.setAttribute('aria-pressed', String(showAllEvents));
  scopeToggle.querySelector('.scope-label').textContent = showAllEvents ? '🌐 Tous' : '📍 Zone visible';
}
scopeToggle.addEventListener('click', () => {
  setShowAllEvents(!showAllEvents);
  updateScopeToggle();
  clearTimeout(fetchDebounceTimer);
  setFetchDebounceTimer(setTimeout(fetchEventsByBbox, 50));
});
updateScopeToggle();

// ── Toggle catégories (Aucune / Toutes) ───────────────────────────────────
document.getElementById('toggle-cats').addEventListener('click', toggleAllCategoryPills);

// ── Init ──────────────────────────────────────────────────────────────────
async function loadEvents() {
  const hadParams = restoreFromURL();
  if (!hadParams) {
    document.getElementById('filter-date-from').value = isoDate(todayJST());
  }
  try {
    await fetchEventsByBbox();
    setBboxFetchEnabled(true);
  } catch (e) {
    document.getElementById('stats').textContent = 'Erreur de chargement.';
    console.error(e);
  }
}

loadEvents();
