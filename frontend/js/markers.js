/* global L */
import { allEvents, showOnlyFavorites, clusterGroup, markerMap } from './state.js';
import { TC_EXCLUDED_CATS } from './config.js';
import { getFavorites, getIcon } from './favorites.js';
import { buildPopup } from './popups.js';
import { getActivePills } from './filters.js';
import { buildEventList } from './events-list.js';

export function renderMarkers() {
  const active = getActivePills();
  const fromS  = document.getElementById('filter-date-from').value || null;
  const toS    = document.getElementById('filter-date-to').value   || null;
  const favs   = getFavorites();

  // Un refetch déclenché par l'autoPan de la bulle reconstruit tous les marqueurs
  // (clearLayers), ce qui fermerait la bulle en cours d'affichage. On mémorise
  // l'événement dont la bulle est ouverte pour la rouvrir après reconstruction.
  let reopenId = null;
  markerMap.forEach((m, id) => { if (m.isPopupOpen()) reopenId = id; });

  clusterGroup.clearLayers();
  markerMap.clear();

  // La carte occupe tout l'écran ; les barres flottent par-dessus. L'autoPan de
  // Leaflet ne connaît que les bords du conteneur, donc la bulle finit clippée
  // sous ces barres. On lui donne un padding égal à leur hauteur réelle (mesurée
  // ici pour s'adapter au desktop/mobile) pour qu'il recentre correctement.
  const topBar    = document.getElementById('top-bar');
  const bottomBar = document.getElementById('bottom-bar');
  const padTop    = (topBar    ? topBar.offsetHeight    : 100) + 24;
  const padBottom = (bottomBar ? bottomBar.offsetHeight : 0)   + 24;
  const popupOpts = {
    maxWidth: 300,
    minWidth: 280,
    autoPanPaddingTopLeft:     L.point(24, padTop),
    autoPanPaddingBottomRight: L.point(24, padBottom),
  };

  const visible = [];

  allEvents.forEach(ev => {
    const hasCoords = ev.latitude != null && ev.longitude != null;
    // Events without coordinates only appear in the list (not the map).
    // Currently only Time Out Tokyo events lack coordinates.
    if (!hasCoords && ev.source !== 'tot') return;

    if (showOnlyFavorites && !favs.has(ev.id)) return;

    const evStart = ev.start_date || ev.date;
    const evEnd   = ev.end_date || evStart;
    if (fromS && evEnd   < fromS) return;
    if (toS   && evStart > toS)   return;

    if (ev.source === 'hanabi') {
      if (!active.has('hanabi')) return;
    } else if (ev.source === 'tot') {
      if (!active.has('tot')) return;
    } else {
      const cats = ((ev.attributes || {}).categories || []).filter(c => !TC_EXCLUDED_CATS.includes(c));
      const onlyFW = TC_EXCLUDED_CATS.every(c => ((ev.attributes || {}).categories || []).includes(c)) && cats.length === 0;
      if (onlyFW) return;
      if (cats.length > 0 && !cats.some(c => active.has(c))) return;
    }

    if (hasCoords) {
      const icon   = getIcon(ev, favs.has(ev.id));
      const marker = L.marker([ev.latitude, ev.longitude], { icon });
      marker.bindPopup(buildPopup(ev), popupOpts);
      clusterGroup.addLayer(marker);
      markerMap.set(ev.id, marker);
    }
    visible.push(ev);
  });

  const tc     = visible.filter(e => e.source === 'tc').length;
  const hanabi = visible.filter(e => e.source === 'hanabi').length;
  const tot    = visible.filter(e => e.source === 'tot').length;
  document.getElementById('stats').innerHTML =
    `<strong>${visible.length}</strong> événement${visible.length !== 1 ? 's' : ''} &nbsp;·&nbsp; ` +
    `<span style="color:var(--tc)">●</span> ${tc} &nbsp;` +
    `<span style="color:var(--hanabi)">●</span> ${hanabi}` +
    (tot ? ` &nbsp;<span style="color:var(--tot)">●</span> ${tot}` : '');

  buildEventList(visible);

  // Rouvrir la bulle préservée, mais SANS autoPan : c'est une simple restauration
  // après re-render, la carte ne doit pas se recentrer dessus (sinon elle « snap »
  // sur la bulle à chaque déplacement de l'utilisateur). Seule l'ouverture initiale
  // au clic recadre. On désactive donc temporairement l'autoPan de la bulle.
  if (reopenId && markerMap.has(reopenId)) {
    const popup = markerMap.get(reopenId).getPopup();
    if (popup) {
      const autoPan = popup.options.autoPan;
      popup.options.autoPan = false;
      markerMap.get(reopenId).openPopup();
      popup.options.autoPan = autoPan;
    }
  }
}
