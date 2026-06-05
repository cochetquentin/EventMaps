/* global L */
import { allEvents, showOnlyFavorites, clusterGroup, markerMap } from './state.js';
import { TC_EXCLUDED_CATS } from './config.js';
import { getFavorites, getIcon } from './favorites.js';
import { buildPopup } from './popups.js';
import { openDrawer } from './drawer.js';
import { getActivePills } from './filters.js';
import { buildEventList } from './events-list.js';

export function renderMarkers() {
  const active = getActivePills();
  const fromS  = document.getElementById('filter-date-from').value || null;
  const toS    = document.getElementById('filter-date-to').value   || null;
  const favs   = getFavorites();

  clusterGroup.clearLayers();
  markerMap.clear();

  const visible = [];

  allEvents.forEach(ev => {
    if (!ev.latitude || !ev.longitude) return;
    if (showOnlyFavorites && !favs.has(ev.id)) return;

    const evStart = ev.start_date || ev.date;
    const evEnd   = ev.end_date || evStart;
    if (fromS && evEnd   < fromS) return;
    if (toS   && evStart > toS)   return;

    if (ev.source === 'hanabi') {
      if (!active.has('hanabi')) return;
    } else {
      const cats = ((ev.attributes || {}).categories || []).filter(c => !TC_EXCLUDED_CATS.includes(c));
      const onlyFW = TC_EXCLUDED_CATS.every(c => ((ev.attributes || {}).categories || []).includes(c)) && cats.length === 0;
      if (onlyFW) return;
      if (cats.length > 0 && !cats.some(c => active.has(c))) return;
    }

    const icon   = getIcon(ev, favs.has(ev.id));
    const marker = L.marker([ev.latitude, ev.longitude], { icon });
    marker.bindPopup(buildPopup(ev), { maxWidth: 300, minWidth: 280 });
    marker.on('click', () => openDrawer(ev));
    clusterGroup.addLayer(marker);
    markerMap.set(ev.id, marker);
    visible.push(ev);
  });

  const tc     = visible.filter(e => e.source === 'tc').length;
  const hanabi = visible.filter(e => e.source === 'hanabi').length;
  document.getElementById('stats').innerHTML =
    `<strong>${visible.length}</strong> événement${visible.length !== 1 ? 's' : ''} &nbsp;·&nbsp; ` +
    `<span style="color:var(--tc)">●</span> ${tc} &nbsp;` +
    `<span style="color:var(--hanabi)">●</span> ${hanabi}`;

  buildEventList(visible);
}
