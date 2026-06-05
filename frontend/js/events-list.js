/* global L */
import { allEvents, map, markerMap, showOnlyFavorites, userPosition, proximityMode } from './state.js';
import { fmtDate, escapeHtml, haversineKm, fmtDistance } from './utils.js';
import { TC_EXCLUDED_CATS, CAT_EMOJI } from './config.js';
import { isFavorite, toggleFavorite, getIcon, updateFavPill } from './favorites.js';
import { renderMarkers } from './markers.js';
import { buildPopup } from './popups.js';
import { openDrawer } from './drawer.js';

function makeCard(ev, inProximity, cardsRow) {
  const card = document.createElement('div');
  card.className = 'event-card';

  const date = fmtDate(ev.start_date || ev.date);
  const attrs = ev.attributes || {};
  const sub = ev.source === 'tc'
    ? [escapeHtml(attrs.location_name), escapeHtml(ev.price)].filter(Boolean).join(' · ')
    : [escapeHtml(ev.venue), escapeHtml(attrs.fireworks_count)].filter(Boolean).join(' · ');

  const distBadge = (inProximity && ev.latitude != null && ev.longitude != null)
    ? `<span class="dist-badge">📍 ${fmtDistance(haversineKm(userPosition.lat, userPosition.lng, ev.latitude, ev.longitude))}</span>`
    : '';

  card.innerHTML = `
    <div class="card-header">
      <div class="card-dot ${ev.source}"></div>
      <div class="card-title">${escapeHtml(ev.title)}</div>
      <button class="fav-btn ${isFavorite(ev.id) ? 'active' : ''}" title="Favoris">${isFavorite(ev.id) ? '★' : '☆'}</button>
    </div>
    <div class="card-meta">${date}${sub ? ' · ' + sub : ''}${distBadge}</div>`;

  card.querySelector('.fav-btn').addEventListener('click', (e) => {
    e.stopPropagation();
    toggleFavorite(ev.id);
    const fav = isFavorite(ev.id);
    e.currentTarget.textContent = fav ? '★' : '☆';
    e.currentTarget.classList.toggle('active', fav);
    const m = markerMap.get(ev.id);
    if (m) {
      m.setIcon(getIcon(ev, fav));
      m.setPopupContent(buildPopup(ev));
      if (m.isPopupOpen()) {
        document.dispatchEvent(new CustomEvent('popup-fav-rebind', { detail: { marker: m } }));
      }
    }
    updateFavPill();
    if (showOnlyFavorites && !fav) renderMarkers();
  });

  card.addEventListener('click', () => {
    map.setView([ev.latitude, ev.longitude], 15, { animate: true });
    const m = markerMap.get(ev.id);
    if (m) setTimeout(() => m.openPopup(), 350);
    document.querySelectorAll('.event-card').forEach(c => c.classList.remove('highlighted'));
    card.classList.add('highlighted');
    if (cardsRow && cardsRow.classList.contains('hidden')) {
      cardsRow.classList.remove('hidden');
      cardsRow.previousElementSibling.classList.remove('collapsed');
    }
    card.scrollIntoView({ behavior: 'smooth', inline: 'nearest', block: 'nearest' });
    openDrawer(ev);
  });

  return card;
}

export function buildEventList(events) {
  const list = document.getElementById('event-list');
  list.innerHTML = '';

  if (!events.length) {
    list.innerHTML = '<div style="font-size:13px;color:var(--muted);padding:12px 16px">Aucun événement</div>';
    return;
  }

  const inProximity = proximityMode && userPosition;

  if (inProximity) {
    // Liste plate triée par distance globale — pas de groupement (évite qu'un groupe
    // avec des événements lointains apparaisse avant des événements proches d'un autre groupe)
    const sorted = [...events].sort((a, b) => {
      const da = (a.latitude != null && a.longitude != null)
        ? haversineKm(userPosition.lat, userPosition.lng, a.latitude, a.longitude)
        : Infinity;
      const db = (b.latitude != null && b.longitude != null)
        ? haversineKm(userPosition.lat, userPosition.lng, b.latitude, b.longitude)
        : Infinity;
      return da - db;
    });
    sorted.forEach(ev => list.appendChild(makeCard(ev, true, null)));
    return;
  }

  // Mode normal — liste groupée par catégorie triée par date
  const groups = new Map();
  events.forEach(ev => {
    let key;
    if (ev.source === 'hanabi') {
      key = 'hanabi';
      if (!groups.has(key)) groups.set(key, { label: '🎆 Hanabi', events: [] });
    } else {
      const cats = ((ev.attributes || {}).categories || []).filter(c => !TC_EXCLUDED_CATS.includes(c));
      key = cats[0] || 'other';
      if (!groups.has(key)) {
        const emoji = CAT_EMOJI[key] || '📌';
        const name = key === 'other' ? 'Divers' : escapeHtml(key.charAt(0).toUpperCase() + key.slice(1));
        groups.set(key, { label: `${emoji} ${name}`, events: [] });
      }
    }
    groups.get(key).events.push(ev);
  });

  const sorted = [...groups.entries()].sort(([ka, a], [kb, b]) => {
    if (ka === 'hanabi') return -1;
    if (kb === 'hanabi') return  1;
    return b.events.length - a.events.length;
  });

  sorted.forEach(([, group]) => {
    group.events.sort((a, b) => (a.start_date || a.date || '').localeCompare(b.start_date || b.date || ''));

    const groupEl = document.createElement('div');
    groupEl.className = 'cat-group';

    const header = document.createElement('div');
    header.className = 'cat-header';
    header.innerHTML = `
      <span class="cat-label">${group.label}</span>
      <span class="cat-count">${group.events.length}</span>
      <span class="cat-chevron">▾</span>`;

    const cardsRow = document.createElement('div');
    cardsRow.className = 'cat-cards';

    group.events.forEach(ev => cardsRow.appendChild(makeCard(ev, false, cardsRow)));

    header.addEventListener('click', () => {
      const isCollapsed = cardsRow.classList.toggle('hidden');
      header.classList.toggle('collapsed', isCollapsed);
    });

    groupEl.appendChild(header);
    groupEl.appendChild(cardsRow);
    list.appendChild(groupEl);
  });
}
