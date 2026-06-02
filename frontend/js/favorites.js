/* global L */
import { iconTC, iconHanabi } from './config.js';

const FAV_KEY = 'eventmaps_favorites';

export function getFavorites() {
  try { return new Set(JSON.parse(localStorage.getItem(FAV_KEY) || '[]')); }
  catch { return new Set(); }
}

export function isFavorite(id) { return getFavorites().has(id); }

export function toggleFavorite(id) {
  const favs = getFavorites();
  if (favs.has(id)) favs.delete(id); else favs.add(id);
  localStorage.setItem(FAV_KEY, JSON.stringify([...favs]));
}

export function getIcon(ev, fav) {
  if (ev.source === 'tc') {
    return fav
      ? L.divIcon({ html: '<div class="m-tc m-fav"></div>',     className: '', iconSize: [16,16], iconAnchor: [8,8],   popupAnchor: [0,-12] })
      : iconTC;
  }
  return fav
    ? L.divIcon({ html: '<div class="m-hanabi m-fav"></div>', className: '', iconSize: [20,20], iconAnchor: [10,10], popupAnchor: [0,-14] })
    : iconHanabi;
}

export function updateFavPill() {
  const pill = document.querySelector('.fav-pill');
  if (!pill) return;
  const count = getFavorites().size;
  pill.textContent = count > 0 ? `⭐ Favoris (${count})` : '⭐ Favoris';
}
