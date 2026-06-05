import { map, setAllEvents } from './state.js';
import { buildPills } from './filters.js';
import { renderMarkers } from './markers.js';

export let bboxFetchEnabled = false;
export let fetchDebounceTimer = null;
let bboxFetchController = null;

export function setBboxFetchEnabled(v) { bboxFetchEnabled = v; }
export function setFetchDebounceTimer(v) { fetchDebounceTimer = v; }

export async function fetchEventsByBbox({ category = null } = {}) {
  if (bboxFetchController) bboxFetchController.abort();
  bboxFetchController = new AbortController();
  const signal = bboxFetchController.signal;
  try {
    // Lire le terme de recherche depuis le DOM à chaque appel pour que tous les
    // chemins de rafraîchissement (moveend, date, reset…) préservent la recherche active.
    const q = document.getElementById('search-input')?.value.trim() || null;
    const b = map.getBounds(), sw = b.getSouthWest(), ne = b.getNorthEast();
    const minLon = Math.max(-180, sw.lng), maxLon = Math.min(180, ne.lng);
    const minLat = Math.max(-90,  sw.lat), maxLat = Math.min(90,  ne.lat);
    // Degenerate bbox (whole-world zoom) → no bbox filter, server returns all upcoming
    const bbox = (minLon < maxLon && minLat < maxLat)
      ? `${minLon},${minLat},${maxLon},${maxLat}`
      : null;
    const PAGE = 500;
    const events = [];
    let offset = 0;
    while (true) {
      const params = { limit: String(PAGE), offset: String(offset) };
      if (bbox) params.bbox = bbox;
      const fromS = document.getElementById('filter-date-from').value;
      if (fromS) params.start_from = fromS;
      const toS = document.getElementById('filter-date-to').value;
      if (toS) params.start_to = toS;
      if (q) params.q = q;
      if (category) params.category = category;
      const res = await fetch(`/events?${new URLSearchParams(params)}`, { signal });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const page = await res.json();
      events.push(...page);
      if (page.length < PAGE) break;
      offset += PAGE;
    }
    setAllEvents(events);
    buildPills();
    renderMarkers();
  } catch (e) {
    if (e.name === 'AbortError') return;
    document.getElementById('stats').textContent = 'Erreur de chargement.';
    console.error(e);
  }
}
