// Météo Tokyo — source de données pour le widget « Context Cards » de l'en-tête.
// Source : Open-Meteo (gratuit, sans clé API, CORS ouvert).
// Échec réseau → fetchWeather() renvoie null ; le widget bascule sur son fallback.
//
// Les phrases affichées vivent dans ./weather-messages.js (facile à enrichir).
import { WEATHER_MESSAGES } from './weather-messages.js';

const LAT = 35.68;
const LON = 139.69;
const URL =
  `https://api.open-meteo.com/v1/forecast?latitude=${LAT}&longitude=${LON}`
  + '&current=temperature_2m,apparent_temperature,relative_humidity_2m,wind_speed_10m,weather_code'
  + '&hourly=precipitation_probability'
  + '&daily=sunrise,sunset,uv_index_max'
  // forecast_days=2 : on récupère aussi le lever du soleil de demain (carte « Sunrise tomorrow »)
  + '&timezone=Asia%2FTokyo&forecast_days=2';

const CACHE_KEY = 'eventmaps-weather';
const CACHE_TTL = 30 * 60 * 1000; // 30 min : Open-Meteo est généreux mais inutile de spammer

// Code météo WMO → emoji + libellé court
export function weatherInfo(code) {
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

export function buildMessage(temp, code, hourly) {
  if (RAIN_CODES(code)) return pick(WEATHER_MESSAGES.rainNow);
  const rainHour = nextRainHour(hourly);
  if (rainHour) return pick(WEATHER_MESSAGES.rainSoon).replace('{h}', rainHour);
  if (temp >= 30) return pick(WEATHER_MESSAGES.hot);
  if (temp <= 6) return pick(WEATHER_MESSAGES.cold);
  if (code <= 2 && temp >= 15 && temp <= 28) return pick(WEATHER_MESSAGES.nice);
  if (code === 3 || code === 45 || code === 48) return pick(WEATHER_MESSAGES.cloudy);
  return pick(WEATHER_MESSAGES.default);
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

// Récupère et normalise la météo Tokyo pour le moteur de Context Cards.
// Renvoie null en cas d'échec réseau / données incomplètes (le widget prend alors
// son fallback), sans lever d'erreur ni faire de bruit.
export async function fetchWeather() {
  try {
    const data = await loadData();
    const temp = data.current?.temperature_2m;
    if (temp == null) return null; // données incomplètes
    const code = data.current?.weather_code ?? 0;
    const { emoji, label } = weatherInfo(code);
    const feels = data.current?.apparent_temperature;
    const humidity = data.current?.relative_humidity_2m;
    const wind = data.current?.wind_speed_10m;
    return {
      temp: Math.round(temp),
      feels: feels == null ? null : Math.round(feels),       // température ressentie
      humidity: humidity == null ? null : Math.round(humidity),
      wind: wind == null ? null : Math.round(wind),          // km/h
      code,
      emoji,
      label,
      hourly: data.hourly,
      // Open-Meteo daily renvoie des tableaux [aujourd'hui, demain] (forecast_days=2).
      daily: {
        sunrise: data.daily?.sunrise ?? [], // [today, tomorrow]
        sunset: data.daily?.sunset ?? [],   // [today, tomorrow]
        uvMax: data.daily?.uv_index_max?.[0] ?? null, // UV max du jour
      },
      message: buildMessage(temp, code, data.hourly),
    };
  } catch (e) {
    // Réseau indisponible / API en erreur : pas de météo, sans bruit
    console.debug('Météo indisponible :', e);
    return null;
  }
}
