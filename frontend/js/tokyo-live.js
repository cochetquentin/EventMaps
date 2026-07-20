// ══════════════════════════════════════════════════════════════════════════
// Tokyo — système générique de « Context Cards » de l'en-tête.
//
// Le moteur n'est PAS un widget météo : c'est un ordonnanceur générique qui affiche,
// une carte à la fois, l'information la plus pertinente selon le contexte. Les cartes
// livrées (météo, heure, soleil, saison, quartier) ne sont que les premiers providers.
// À terme il pourra afficher n'importe quelle info contextuelle (événements, transports,
// lieux, alertes, éditorial…) SANS modification du moteur : il suffit d'enregistrer un
// nouvel objet provider dans le tableau `providers`.
//
// Contrat d'un provider :
//   {
//     id: 'weather',            // identifiant unique
//     category: 'weather',      // famille (sert à l'anti-répétition)
//     priority: 10,             // fréquence relative d'apparition
//     importance: 'normal',     // low | normal | high | critical (peut préempter)
//     ttl: 30 * MINUTE,         // durée de validité du dernier build (cache)
//     async build(ctx) { ... }  // sync OU async ; renvoie une carte ou null (hors rotation)
//   }
//   carte = { icon, line1, line2? }
//   ctx   = { weather, now, center, zoom, events }
// ══════════════════════════════════════════════════════════════════════════
import { map, allEvents } from './state.js';
import { escapeHtml } from './utils.js';
import { fetchWeather } from './weather.js';
import { seasonFor, describeDistrict } from './tokyo-live-data.js';
import { todayJST } from './utils.js';

const SECOND = 1000;
const MINUTE = 60 * SECOND;
const HOUR = 60 * MINUTE;

const ROTATE_MS = 12 * SECOND;   // cadence de base (10–15 s)
const ANIM_MS = 260;             // transition quasi invisible (léger fondu + slide)
const MOVE_DEBOUNCE_MS = 450;    // anti-spam sur les déplacements de carte
const WEATHER_REFRESH_MS = 30 * MINUTE;
const RECENT_WINDOW = 2;         // taille du cooldown par catégorie

// Libellé permanent du widget : 'none' (préféré) | 'now' | 'live'.
// Le moteur ne dépend jamais de cette valeur.
const TITLE_MODE = 'none';
const TITLES = { now: 'Tokyo Now', live: 'Tokyo Live' };

const IMPORTANCE_RANK = { low: 0, normal: 1, high: 2, critical: 3 };
const impRank = (x) => IMPORTANCE_RANK[x] ?? 1;

// ── Ordonnancement (pur, testable) ─────────────────────────────────────────

// Choisit l'id de la prochaine carte parmi les providers dont la carte est disponible.
// Règles : forçage > préemption (importance) > variété (cooldown catégorie) > cumul de
// priorité (stride). Ne renvoie jamais deux fois d'affilée la même carte.
export function pickNext(providers, available, state) {
  // 1. Forçage explicite (ex. le quartier juste après un déplacement de carte)
  if (state.forcedId && available.has(state.forcedId)) return state.forcedId;

  // 2. Préemption : une carte importante disponible passe devant la rotation normale
  const urgent = providers
    .filter((p) => available.has(p.id) && impRank(p.importance) >= impRank('high') && p.id !== state.lastId)
    .sort((a, b) => impRank(b.importance) - impRank(a.importance) || b.priority - a.priority);
  if (urgent.length) return urgent[0].id;

  // 3. Éligibles : disponibles, différents de la dernière carte, catégorie hors cooldown
  const recent = new Set(state.recent);
  const base = providers.filter((p) => available.has(p.id) && p.id !== state.lastId);
  let pool = base.filter((p) => !recent.has(p.category));
  if (!pool.length) pool = base;                                   // tout en cooldown
  if (!pool.length) pool = providers.filter((p) => available.has(p.id)); // dernier recours

  // 4. Stride : on prend le plus haut cumul de priorité
  let best = null;
  let bestCredit = -Infinity;
  for (const p of pool) {
    const c = state.credits[p.id] || 0;
    if (c > bestCredit) { bestCredit = c; best = p; }
  }
  return best ? best.id : null;
}

// Fabrique un ordonnanceur avec état interne (crédits stride + cooldown catégorie).
export function createScheduler(providers) {
  const credits = {};
  providers.forEach((p) => { credits[p.id] = 0; });
  let lastId = null;
  const recent = [];

  return {
    next(available, opts = {}) {
      const avail = available instanceof Set ? available : new Set(available);
      // Cumul de priorité pour chaque éligible (les exclus continuent de monter et
      // finiront par gagner leur tour → équité proportionnelle sans famine).
      for (const p of providers) {
        if (avail.has(p.id)) credits[p.id] += p.priority;
      }
      const id = pickNext(providers, avail, { credits, recent, lastId, forcedId: opts.forcedId });
      if (id) {
        credits[id] = 0;
        lastId = id;
        const cat = providers.find((p) => p.id === id)?.category;
        recent.push(cat);
        while (recent.length > RECENT_WINDOW) recent.shift();
      }
      return id;
    },
  };
}

// ── Helpers de rendu ───────────────────────────────────────────────────────

function formatJST(date) {
  return new Intl.DateTimeFormat('fr-FR', {
    timeZone: 'Asia/Tokyo', hour: '2-digit', minute: '2-digit', hour12: false,
  }).format(date);
}

// "2026-07-20T04:39" → "04:39" (les horaires Open-Meteo sont déjà en heure de Tokyo)
const hhmm = (iso) => (iso ? iso.slice(11, 16) : '');

// ── Providers livrés ───────────────────────────────────────────────────────

// Alterne carte éditoriale de zone / formulation naturelle, pour varier.
let placeEditorialTurn = true;

function buildPlaceCard(ctx) {
  if (!ctx.center) return null;
  const r = describeDistrict(ctx.center.lat, ctx.center.lon, ctx.zoom);
  if (!r) return null;
  if (r.tag && placeEditorialTurn) {
    placeEditorialTurn = false;
    return { icon: r.tag.emoji, line1: r.tag.text, line2: `${r.name} ${r.kanji}` };
  }
  placeEditorialTurn = true;
  return { icon: r.natural.emoji, line1: r.natural.text, line2: r.kanji };
}

function buildSunCard(ctx) {
  const d = ctx.weather?.daily;
  if (!d || (!d.sunrise && !d.sunset)) return null;
  const nowHM = formatJST(ctx.now);
  const sunriseHM = hhmm(d.sunrise);
  const sunsetHM = hhmm(d.sunset);
  // Avant le lever (petit matin) → on annonce le lever ; sinon → le coucher.
  if (sunriseHM && nowHM < sunriseHM) {
    return { icon: '🌅', line1: `Sunrise ${sunriseHM}`, line2: 'Tokyo · JST' };
  }
  if (sunsetHM) return { icon: '🌇', line1: `Sunset ${sunsetHM}`, line2: 'Tokyo · JST' };
  return { icon: '🌅', line1: `Sunrise ${sunriseHM}`, line2: 'Tokyo · JST' };
}

function makeProviders() {
  return [
    {
      id: 'weather', category: 'weather', priority: 10, importance: 'normal', ttl: 30 * MINUTE,
      build: (ctx) => (ctx.weather
        ? { icon: ctx.weather.emoji, line1: `${ctx.weather.temp}°`, line2: ctx.weather.message }
        : null),
    },
    {
      id: 'time', category: 'time', priority: 8, importance: 'normal', ttl: MINUTE,
      build: (ctx) => ({ icon: '🕒', line1: formatJST(ctx.now), line2: 'Tokyo · JST' }),
    },
    {
      id: 'sun', category: 'sun', priority: 6, importance: 'low', ttl: 30 * MINUTE,
      build: buildSunCard,
    },
    {
      id: 'season', category: 'season', priority: 3, importance: 'low', ttl: 24 * HOUR,
      build: () => {
        const s = seasonFor(todayJST());
        return { icon: s.emoji, line1: s.label, line2: s.note };
      },
    },
    {
      id: 'place', category: 'place', priority: 2, importance: 'normal', ttl: 24 * HOUR,
      build: buildPlaceCard, // invalidé explicitement à chaque déplacement de carte
    },
    {
      id: 'fallback', category: 'fallback', priority: 0, importance: 'low', ttl: Infinity,
      build: () => ({ icon: '📍', line1: 'Tokyo', line2: "Discover what's happening today." }),
    },
  ];
}

// ── Moteur (effets de bord : DOM, carte, timers) ───────────────────────────

export function initTokyoLive() {
  const el = document.getElementById('tokyo-live');
  if (!el) return;

  const reduceMotion = typeof matchMedia === 'function'
    && matchMedia('(prefers-reduced-motion: reduce)').matches;

  const providers = makeProviders();
  const scheduler = createScheduler(providers);
  const cache = {}; // id → { card, at, stale }
  let weather = null;

  // Montage du DOM interne (le conteneur #tokyo-live existe déjà, vide, dans l'HTML)
  const titleHTML = TITLE_MODE !== 'none' && TITLES[TITLE_MODE]
    ? `<span class="tlive-title">${TITLES[TITLE_MODE]}</span>` : '';
  el.innerHTML =
    '<span class="tlive-dot" aria-hidden="true"></span>'
    + titleHTML
    + '<div class="tlive-stage" role="status" aria-live="polite"><div class="tlive-card"></div></div>';
  el.hidden = false; // le fallback garantit un contenu dès le départ

  const cardEl = el.querySelector('.tlive-card');

  function buildCtx() {
    const now = new Date();
    let center = null;
    let zoom = null;
    if (map) {
      const c = map.getCenter();
      center = { lat: c.lat, lon: c.lng };
      zoom = map.getZoom();
    }
    return { weather, now, center, zoom, events: allEvents };
  }

  // Rafraîchit le cache des cartes et renvoie l'ensemble des ids disponibles.
  function computeAvailable() {
    const ctx = buildCtx();
    const now = Date.now();
    const available = new Set();
    for (const p of providers) {
      const c = cache[p.id];
      const fresh = c && !c.stale && (now - c.at) < p.ttl;
      if (!fresh) {
        let card = null;
        try { card = p.build(ctx) || null; } catch { card = null; }
        cache[p.id] = { card, at: now, stale: false };
      }
      if (cache[p.id].card) available.add(p.id);
    }
    return available;
  }

  function cardHTML(card) {
    const l2 = card.line2
      ? `<span class="tlive-l2">${escapeHtml(card.line2)}</span>` : '';
    return `<span class="tlive-ico" aria-hidden="true">${card.icon}</span>`
      + `<span class="tlive-lines"><span class="tlive-l1">${escapeHtml(card.line1)}</span>${l2}</span>`;
  }

  let swapTimer = null;
  function render(card) {
    if (!card) return;
    const html = cardHTML(card);
    if (reduceMotion) { cardEl.innerHTML = html; return; }
    clearTimeout(swapTimer);
    cardEl.classList.add('is-leaving');
    swapTimer = setTimeout(() => {
      cardEl.innerHTML = html;
      cardEl.classList.remove('is-leaving');
      cardEl.classList.add('is-entering');
      // Force un reflow puis retire la classe → transition douce vers l'état normal.
      void cardEl.offsetWidth;
      cardEl.classList.remove('is-entering');
    }, ANIM_MS / 2);
  }

  function advance(opts = {}) {
    const available = computeAvailable();
    const id = scheduler.next(available, opts);
    if (id) render(cache[id].card);
  }

  // ── Boucle temporisée ──
  let timer = null;
  let paused = false;
  function schedule() { clearTimeout(timer); timer = setTimeout(tick, ROTATE_MS); }
  function tick() { if (!paused) advance(); schedule(); }
  function kick(opts) { advance(opts); schedule(); }

  // ── Interactions ──
  el.addEventListener('mouseenter', () => { paused = true; clearTimeout(timer); });
  el.addEventListener('mouseleave', () => { paused = false; schedule(); });
  el.addEventListener('click', () => kick());
  if (typeof document.addEventListener === 'function') {
    document.addEventListener('visibilitychange', () => {
      if (document.hidden) { paused = true; clearTimeout(timer); }
      else { paused = false; schedule(); }
    });
  }

  // Déplacement de carte → la prochaine carte affichée est le quartier/contexte.
  if (map && typeof map.on === 'function') {
    let moveTimer = null;
    map.on('moveend', () => {
      clearTimeout(moveTimer);
      moveTimer = setTimeout(() => {
        if (cache.place) cache.place.stale = true;
        const available = computeAvailable();
        if (!available.has('place')) return; // dézoomé : rien de pertinent, on ne bouscule pas
        const id = scheduler.next(available, { forcedId: 'place' });
        if (id) { render(cache[id].card); schedule(); }
      }, MOVE_DEBOUNCE_MS);
    });
  }

  // ── Météo (asynchrone) ──
  fetchWeather().then((w) => {
    if (!w) return;
    weather = w;
    if (cache.weather) cache.weather.stale = true;
    if (cache.sun) cache.sun.stale = true;
    kick({ forcedId: 'weather' }); // on montre la météo dès qu'elle arrive
  });
  setInterval(() => {
    fetchWeather().then((w) => {
      if (!w) return;
      weather = w;
      if (cache.weather) cache.weather.stale = true;
      if (cache.sun) cache.sun.stale = true;
    });
  }, WEATHER_REFRESH_MS);

  // Premier affichage immédiat (fallback garanti) puis rotation.
  advance();
  schedule();
}
