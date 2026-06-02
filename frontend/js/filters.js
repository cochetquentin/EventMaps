import { allEvents, deactivatedPills, showOnlyFavorites, setShowOnlyFavorites } from './state.js';
import { TC_EXCLUDED_CATS, CAT_EMOJI } from './config.js';
import { getFavorites } from './favorites.js';
import { renderMarkers } from './markers.js';

export function getActivePills() {
  const s = new Set();
  document.querySelectorAll('.pill.active').forEach(p => s.add(p.dataset.type));
  return s;
}

export function buildPills() {
  const container = document.getElementById('pills');
  container.innerHTML = '';

  // Favorites pill — toggles showOnlyFavorites, not in deactivatedPills
  const favCount = getFavorites().size;
  const favPill = document.createElement('button');
  favPill.className = 'pill fav-pill' + (showOnlyFavorites ? ' active' : '');
  favPill.textContent = favCount > 0 ? `⭐ Favoris (${favCount})` : '⭐ Favoris';
  favPill.addEventListener('click', () => {
    setShowOnlyFavorites(!showOnlyFavorites);
    favPill.classList.toggle('active', showOnlyFavorites);
    renderMarkers();
  });
  container.appendChild(favPill);

  addPill(container, 'hanabi', '🎆 Hanabi', true);

  const catCounts = {};
  allEvents.forEach(ev => {
    if (ev.source !== 'tc') return;
    ((ev.attributes || {}).categories || []).forEach(c => { catCounts[c] = (catCounts[c] || 0) + 1; });
  });

  Object.entries(catCounts)
    .filter(([c]) => !TC_EXCLUDED_CATS.includes(c))
    .sort((a, b) => b[1] - a[1])
    .forEach(([cat]) => addPill(container, cat, `${CAT_EMOJI[cat] || ''} ${cat}`));

  // Restore deactivated state after rebuild
  container.querySelectorAll('.pill').forEach(p => {
    if (deactivatedPills.has(p.dataset.type)) p.classList.remove('active');
  });
}

export function addPill(container, type, label, isHanabi = false) {
  const btn = document.createElement('button');
  btn.className = 'pill active' + (isHanabi ? ' h' : '');
  btn.dataset.type = type;
  btn.textContent = label;
  btn.addEventListener('click', () => {
    btn.classList.toggle('active');
    if (btn.classList.contains('active')) deactivatedPills.delete(type);
    else deactivatedPills.add(type);
    renderMarkers();
  });
  container.appendChild(btn);
}
