import { deactivatedPills, showOnlyFavorites, setShowOnlyFavorites } from './state.js';

/**
 * Encode l'état courant des filtres dans les query params de l'URL.
 * Utilise replaceState pour ne pas polluer l'historique à chaque frappe.
 */
export function updateURL() {
  const params = new URLSearchParams();
  const from = document.getElementById('filter-date-from').value;
  const to   = document.getElementById('filter-date-to').value;
  const q    = document.getElementById('search-input').value.trim();

  if (from) params.set('from', from);
  if (to)   params.set('to', to);
  if (q)    params.set('q', q);

  const off = [...deactivatedPills].join(',');
  if (off) params.set('off', off);

  if (showOnlyFavorites) params.set('favs', '1');

  const qs = params.toString();
  window.history.replaceState(null, '', qs ? `?${qs}` : location.pathname);
}

/**
 * Restaure les filtres depuis les query params de l'URL courante.
 * Doit être appelé avant le premier fetch.
 * @returns {boolean} true si des paramètres URL ont été trouvés et appliqués
 */
export function restoreFromURL() {
  const params = new URLSearchParams(location.search);
  if (!params.size) return false;

  const from = params.get('from');
  const to   = params.get('to');
  const q    = params.get('q');
  const off  = params.get('off');
  const favs = params.get('favs');

  if (from) document.getElementById('filter-date-from').value = from;
  if (to)   document.getElementById('filter-date-to').value   = to;
  if (q)    document.getElementById('search-input').value     = q;
  if (off)  off.split(',').filter(Boolean).forEach(t => deactivatedPills.add(t));
  if (favs === '1') setShowOnlyFavorites(true);

  return true;
}
