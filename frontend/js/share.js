import { deactivatedPills, showOnlyFavorites, setShowOnlyFavorites } from './state.js';
import { isoDate, todayJST } from './utils.js';

const KNOWN_PARAMS = ['from', 'to', 'q', 'off', 'favs'];

/**
 * Encode l'état courant des filtres dans les query params de l'URL.
 * Utilise replaceState pour ne pas polluer l'historique à chaque frappe.
 * La date `from` n'est pas sérialisée si elle correspond à la valeur par défaut
 * (aujourd'hui en JST), pour éviter de "figer" la date dans l'URL après init/reset.
 */
export function updateURL() {
  const params = new URLSearchParams();
  const from = document.getElementById('filter-date-from').value;
  const to   = document.getElementById('filter-date-to').value;
  const q    = document.getElementById('search-input').value.trim();

  const today = isoDate(todayJST());
  if (from && from !== today) params.set('from', from);
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
  if (!KNOWN_PARAMS.some(k => params.has(k))) return false;

  const from = params.get('from');
  const to   = params.get('to');
  const q    = params.get('q');
  const off  = params.get('off');
  const favs = params.get('favs');

  document.getElementById('filter-date-from').value = from || isoDate(todayJST());
  if (to)   document.getElementById('filter-date-to').value   = to;
  if (q)    document.getElementById('search-input').value     = q;
  if (off)  off.split(',').filter(Boolean).forEach(t => deactivatedPills.add(t));
  if (favs === '1') setShowOnlyFavorites(true);

  return true;
}
