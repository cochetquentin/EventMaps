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

// Catégories connues : on part de la liste curée (CAT_EMOJI) et on l'enrichit au fil
// des données chargées, SANS jamais retirer. Ainsi toutes les catégories sont
// affichées d'emblée et les pastilles restent stables quand on zoome/déplace la carte
// (avant, elles apparaissaient/disparaissaient selon les événements de la bbox, ce qui
// empêchait de désélectionner une catégorie absente de la vue courante).
const knownCategories = new Set(
  Object.keys(CAT_EMOJI).filter(c => c !== 'hanabi' && !TC_EXCLUDED_CATS.includes(c)),
);

export function buildPills() {
  const container = document.getElementById('pills');
  container.innerHTML = '';

  // Comptes sur les événements actuellement chargés (bbox visible)
  const catCounts = {};
  let hanabiN = 0;
  let totN = 0;
  allEvents.forEach(ev => {
    if (ev.source === 'hanabi') { hanabiN++; return; }
    if (ev.source === 'tot') { totN++; return; }
    ((ev.attributes || {}).categories || []).forEach(c => {
      if (TC_EXCLUDED_CATS.includes(c)) return;
      catCounts[c] = (catCounts[c] || 0) + 1;
      knownCategories.add(c);   // enrichit la liste (grow-only)
    });
  });

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

  addPill(container, 'hanabi', `🎆 Hanabi (${hanabiN})`, true);
  addPill(container, 'tot', `🗼 Time Out (${totN})`, true);

  // Toutes les catégories connues, ordre stable : les curées d'abord (ordre de
  // CAT_EMOJI), puis les éventuelles autres par ordre alphabétique. Le compteur
  // entre parenthèses = nombre d'événements de cette catégorie actuellement à l'écran.
  const order = Object.keys(CAT_EMOJI);
  [...knownCategories]
    .sort((a, b) => {
      const ia = order.indexOf(a);
      const ib = order.indexOf(b);
      if (ia !== -1 && ib !== -1) return ia - ib;
      if (ia !== -1) return -1;
      if (ib !== -1) return 1;
      return a.localeCompare(b);
    })
    .forEach(cat => {
      const n = catCounts[cat] || 0;
      addPill(container, cat, `${CAT_EMOJI[cat] || ''} ${cat} (${n})`);
    });

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
