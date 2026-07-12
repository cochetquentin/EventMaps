import { allEvents, deactivatedPills, showOnlyFavorites, setShowOnlyFavorites } from './state.js';
import { TC_EXCLUDED_CATS, CAT_EMOJI } from './config.js';
import { getFavorites } from './favorites.js';
import { renderMarkers } from './markers.js';
import { updateURL } from './share.js';

export function getActivePills() {
  const s = new Set();
  document.querySelectorAll('.pill.active').forEach(p => s.add(p.dataset.type));
  return s;
}

// Met à jour le libellé du bouton « Aucune / Toutes » selon l'état des pills catégories
export function updateCatToggle() {
  const btn = document.getElementById('toggle-cats');
  if (!btn) return;
  const catPills = document.querySelectorAll('#pills .pill:not(.fav-pill)');
  const anyActive = [...catPills].some(p => p.classList.contains('active'));
  btn.textContent = anyActive ? 'Aucune' : 'Toutes';
  btn.classList.toggle('all-off', !anyActive);
}

// Bascule toutes les catégories (hanabi/tot/catégories) d'un coup — favoris exclu
export function toggleAllCategoryPills() {
  const catPills = [...document.querySelectorAll('#pills .pill:not(.fav-pill)')];
  const anyActive = catPills.some(p => p.classList.contains('active'));
  catPills.forEach(p => {
    if (anyActive) { p.classList.remove('active'); deactivatedPills.add(p.dataset.type); }
    else { p.classList.add('active'); deactivatedPills.delete(p.dataset.type); }
  });
  updateCatToggle();
  renderMarkers();
  updateURL();
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
    updateURL();
  });
  container.appendChild(favPill);

  addPill(container, 'hanabi', '🎆 Hanabi', true);
  addPill(container, 'tot', '🗼 Time Out', true);

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

  updateCatToggle();
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
    updateCatToggle();
    renderMarkers();
    updateURL();
  });
  container.appendChild(btn);
}
