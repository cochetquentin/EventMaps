// Widget météo Tokyo — remplit l'en-tête desktop avec la météo courante et un petit
// mot contextuel. Source : Open-Meteo (gratuit, sans clé API, CORS ouvert).
// Échec réseau → le widget reste masqué, aucune conséquence sur le reste de l'app.

const LAT = 35.68;
const LON = 139.69;
const URL =
  `https://api.open-meteo.com/v1/forecast?latitude=${LAT}&longitude=${LON}`
  + '&current=temperature_2m,weather_code'
  + '&hourly=precipitation_probability'
  + '&timezone=Asia%2FTokyo&forecast_days=1';

const CACHE_KEY = 'eventmaps-weather';
const CACHE_TTL = 30 * 60 * 1000; // 30 min : Open-Meteo est généreux mais inutile de spammer

// Code météo WMO → emoji + libellé court
function weatherInfo(code) {
  if (code === 0) return { emoji: '☀️', label: 'ensoleillé' };
  if (code <= 2) return { emoji: '🌤️', label: 'peu nuageux' };
  if (code === 3) return { emoji: '☁️', label: 'couvert' };
  if (code === 45 || code === 48) return { emoji: '🌫️', label: 'brouillard' };
  if (code >= 51 && code <= 57) return { emoji: '🌦️', label: 'bruine' };
  if (code >= 61 && code <= 67) return { emoji: '🌧️', label: 'pluie' };
  if (code >= 71 && code <= 77) return { emoji: '❄️', label: 'neige' };
  if (code >= 80 && code <= 82) return { emoji: '🌦️', label: 'averses' };
  if (code >= 85 && code <= 86) return { emoji: '🌨️', label: 'neige' };
  if (code >= 95) return { emoji: '⛈️', label: 'orage' };
  return { emoji: '🌡️', label: '' };
}

const RAIN_CODES = (c) => (c >= 51 && c <= 67) || (c >= 80 && c <= 82) || c >= 95;

// Petite base de mots mignons selon la situation — on en pioche un au hasard
const MESSAGES = {
  rainSoon: (h) => [
    `Pluie prévue vers ${h} ☔ — prévois un plan en intérieur`,
    `Averses annoncées vers ${h} — musée ou café peut-être ?`,
    `Ça va tomber vers ${h} 🌧️ — garde un parapluie`,
  ],
  rainNow: [
    'Il pleut 🌧️ — parapluie obligatoire !',
    'Temps à rester au chaud ☕ — expo ou izakaya ?',
    'Pluie en cours — parfait pour un musée 🖼️',
  ],
  hot: [
    'Grosse chaleur 🥵 — hydrate-toi bien !',
    'Il fait chaud — cherche l’ombre et bois de l’eau 💧',
    'Canicule — privilégie l’intérieur climatisé ❄️',
  ],
  cold: [
    'Ça caille 🧣 — couvre-toi bien',
    'Froid glacial — un ramen bien chaud ? 🍜',
    'Brrr ❄️ — pense aux couches',
  ],
  nice: [
    'Temps idéal pour sortir 🌸 — profites-en !',
    'Grand beau ☀️ — direction l’extérieur !',
    'Journée parfaite pour flâner 🚶',
  ],
  cloudy: [
    'Ciel gris ☁️ — parfait pour un musée',
    'Un peu couvert — expo ou café cosy ?',
    'Temps doux et nuageux — balade tranquille 🚶',
  ],
  default: ['Belle journée à Tokyo ✨'],
};

const pick = (arr) => arr[Math.floor(Math.random() * arr.length)];

// Cherche la première heure à venir avec forte probabilité de pluie → "15h"
function nextRainHour(hourly) {
  if (!hourly || !hourly.time) return null;
  const now = Date.now();
  for (let i = 0; i < hourly.time.length; i++) {
    const t = new Date(hourly.time[i]).getTime();
    if (t < now) continue;
    if ((hourly.precipitation_probability?.[i] ?? 0) >= 60) {
      return `${new Date(hourly.time[i]).getHours()}h`;
    }
  }
  return null;
}

function buildMessage(temp, code, hourly) {
  if (RAIN_CODES(code)) return pick(MESSAGES.rainNow);
  const rainHour = nextRainHour(hourly);
  if (rainHour) return pick(MESSAGES.rainSoon(rainHour));
  if (temp >= 30) return pick(MESSAGES.hot);
  if (temp <= 6) return pick(MESSAGES.cold);
  if (code <= 2 && temp >= 15 && temp <= 28) return pick(MESSAGES.nice);
  if (code === 3 || code === 45 || code === 48) return pick(MESSAGES.cloudy);
  return pick(MESSAGES.default);
}

async function loadData() {
  // Cache local pour limiter les requêtes
  try {
    const cached = JSON.parse(localStorage.getItem(CACHE_KEY) || 'null');
    if (cached && Date.now() - cached.ts < CACHE_TTL) return cached.data;
  } catch { /* cache illisible : on refetch */ }

  const res = await fetch(URL);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const data = await res.json();
  try {
    localStorage.setItem(CACHE_KEY, JSON.stringify({ ts: Date.now(), data }));
  } catch { /* quota storage plein : tant pis */ }
  return data;
}

export async function initWeather() {
  const el = document.getElementById('weather');
  if (!el) return;
  try {
    const data = await loadData();
    const temp = data.current?.temperature_2m;
    const code = data.current?.weather_code ?? 0;
    if (temp == null) return; // données incomplètes : on laisse masqué
    const { emoji, label } = weatherInfo(code);
    const msg = buildMessage(temp, code, data.hourly);
    el.innerHTML =
      `<span class="weather-icon" aria-hidden="true">${emoji}</span>`
      + `<span class="weather-temp">${Math.round(temp)}°</span>`
      + `<span class="weather-msg">${msg}</span>`;
    el.title = `Tokyo — ${label} ${Math.round(temp)}°C`;
    el.hidden = false;
  } catch (e) {
    // Réseau indisponible / API en erreur : on garde le widget masqué, sans bruit
    console.debug('Météo indisponible :', e);
  }
}
