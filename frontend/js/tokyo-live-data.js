// Données statiques du système de Context Cards de l'en-tête (quartiers + saisons).
// Tout est extensible ici sans toucher au moteur (tokyo-live.js) :
//   - ajoute un quartier dans TOKYO_DISTRICTS (avec un `tag` optionnel pour une carte
//     éditoriale de zone) ;
//   - ajoute/ajuste une saison dans SEASONS.
import { haversineKm } from './utils.js';

// ── Quartiers de Tokyo ─────────────────────────────────────────────────────
// name/kanji : affichage. lat/lon : centroïde, pour trouver le plus proche du centre
// de la carte. tag (optionnel) : phrase éditoriale qui « raconte » la zone.
export const TOKYO_DISTRICTS = [
  { name: 'Shibuya',    kanji: '渋谷',   lat: 35.6595, lon: 139.7005 },
  { name: 'Shinjuku',   kanji: '新宿',   lat: 35.6896, lon: 139.7006 },
  { name: 'Harajuku',   kanji: '原宿',   lat: 35.6702, lon: 139.7027 },
  { name: 'Ginza',      kanji: '銀座',   lat: 35.6717, lon: 139.7650 },
  { name: 'Marunouchi', kanji: '丸の内', lat: 35.6812, lon: 139.7671 },
  { name: 'Akihabara',  kanji: '秋葉原', lat: 35.6987, lon: 139.7730 },
  { name: 'Roppongi',   kanji: '六本木', lat: 35.6628, lon: 139.7315 },
  { name: 'Ikebukuro',  kanji: '池袋',   lat: 35.7295, lon: 139.7109 },
  { name: 'Nakameguro', kanji: '中目黒', lat: 35.6440, lon: 139.6990 },
  { name: 'Odaiba',     kanji: 'お台場', lat: 35.6297, lon: 139.7752 },
  { name: 'Ueno',    kanji: '上野', lat: 35.7141, lon: 139.7774, tag: { emoji: '🌸', text: 'Ueno is entering peak bloom.' } },
  { name: 'Asakusa', kanji: '浅草', lat: 35.7118, lon: 139.7967, tag: { emoji: '🏮', text: 'Explore historic Asakusa.' } },
  { name: 'Sumida',  kanji: '墨田', lat: 35.7101, lon: 139.8017, tag: { emoji: '🎆', text: 'Sumida prepares for fireworks.' } },
];

// Renvoie le quartier le plus proche d'un point + sa distance en km.
export function nearestDistrict(lat, lon) {
  let best = null;
  let bestKm = Infinity;
  for (const d of TOKYO_DISTRICTS) {
    const km = haversineKm(lat, lon, d.lat, d.lon);
    if (km < bestKm) { bestKm = km; best = d; }
  }
  return { district: best, km: bestKm };
}

// Formulation naturelle du quartier exploré selon le zoom et la distance au centre.
// Renvoie null quand rien n'est pertinent (vue « tout Tokyo » ou aucun quartier à
// proximité) — on n'invente jamais une fausse précision.
//   { name, kanji, natural: { emoji, text }, tag: { emoji, text } | null }
export function describeDistrict(lat, lon, zoom) {
  if (zoom == null || zoom < 12) return null;      // dézoomé : vue trop large
  const { district, km } = nearestDistrict(lat, lon);
  if (!district || km > 4) return null;            // rien de pertinent tout près
  const verb = km <= 1 ? 'Exploring' : km <= 2.2 ? 'Around' : 'Near';
  return {
    name: district.name,
    kanji: district.kanji,
    natural: { emoji: '📍', text: `${verb} ${district.name}` },
    // Carte éditoriale seulement si on est bien sur la zone taguée
    tag: district.tag && km <= 1.5 ? district.tag : null,
  };
}

// ── Saisons de Tokyo ───────────────────────────────────────────────────────
// Plages [mois, jour] → [mois, jour] (bornes incluses), couverture complète de l'année,
// sans chevauchement d'année (Illuminations séparé de Winter au 1er janvier).
export const SEASONS = [
  { emoji: '❄️', label: 'Winter',        note: 'Crisp winter days',  from: [1, 1],   to: [3, 19] },
  { emoji: '🌸', label: 'Sakura',        note: 'Peak bloom season',  from: [3, 20],  to: [4, 10] },
  { emoji: '🍃', label: 'Fresh green',   note: 'Shinryoku season',   from: [4, 11],  to: [5, 31] },
  { emoji: '☔', label: 'Tsuyu',         note: 'Rainy season',       from: [6, 1],   to: [7, 20] },
  { emoji: '🎆', label: 'Hanabi',        note: 'Fireworks season',   from: [7, 21],  to: [8, 31] },
  { emoji: '🍂', label: 'Autumn',        note: 'Autumn breeze',      from: [9, 1],   to: [10, 31] },
  { emoji: '🍁', label: 'Momiji',        note: 'Autumn leaves',      from: [11, 1],  to: [11, 30] },
  { emoji: '✨', label: 'Illuminations', note: 'Winter lights',      from: [12, 1],  to: [12, 31] },
];

// Saison correspondant à une date. Lit le mois/jour en UTC pour coller à la convention
// de todayJST() (qui encode la date JST dans les champs UTC).
export function seasonFor(date) {
  const key = (date.getUTCMonth() + 1) * 100 + date.getUTCDate();
  for (const s of SEASONS) {
    const lo = s.from[0] * 100 + s.from[1];
    const hi = s.to[0] * 100 + s.to[1];
    if (key >= lo && key <= hi) return s;
  }
  return SEASONS[0]; // couverture complète : fallback théorique
}
