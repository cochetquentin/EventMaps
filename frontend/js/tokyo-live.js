// ══════════════════════════════════════════════════════════════════════════
// Tokyo — « Context Bar » de l'en-tête.
//
// Ce n'est PAS un widget météo : c'est une barre de contexte qui occupe l'espace
// disponible du header entre le logo et les boutons. Deux familles de providers :
//
//   • Context providers  → toujours visibles (météo, heure JST, quartier exploré).
//                          Rendus côte à côte, jamais animés, mis à jour en place.
//   • Editorial providers → un seul bloc rotatif à droite (flex: 1). Change
//                          discrètement toutes les ~12 s (léger fondu + slide).
//
// Le contexte reste stable ; seul le message éditorial évolue → le header paraît
// vivant sans donner l'impression que toute l'interface bouge.
//
// EXTENSIBLE : ajouter une info = enregistrer un provider dans makeContextProviders()
// (bloc permanent) ou makeEditorialProviders() (rotation), sans toucher au moteur.
//
// Contrat d'un provider :
//   context  : { id, build(ctx) -> { icon, main, sub? } | null }
//   editorial: { id, category, priority, importance, build(ctx) -> { icon, text } | null }
//   ctx = { weather, now, center, zoom, events }
// ══════════════════════════════════════════════════════════════════════════
import { map, allEvents } from './state.js';
import { escapeHtml, todayJST } from './utils.js';
import { fetchWeather } from './weather.js';
import { seasonFor, describeDistrict } from './tokyo-live-data.js';

const SECOND = 1000;
const MINUTE = 60 * SECOND;

const ROTATE_MS = 12 * SECOND;          // rotation du bloc éditorial (10–15 s)
const ANIM_MS = 300;                    // transition quasi invisible (fondu + slide)
const CONTEXT_REFRESH_MS = 15 * SECOND; // rafraîchissement du contexte (surtout l'heure)
const MOVE_DEBOUNCE_MS = 350;           // anti-spam sur les déplacements de carte
const WEATHER_REFRESH_MS = 30 * MINUTE;
const RECENT_WINDOW = 2;                // cooldown par catégorie (éditorial)

const IMPORTANCE_RANK = { low: 0, normal: 1, high: 2, critical: 3 };
const impRank = (x) => IMPORTANCE_RANK[x] ?? 1;

// ── Ordonnancement du bloc éditorial (pur, testable) ───────────────────────

// Choisit l'id du prochain message éditorial parmi ceux dont la carte est disponible.
// Règles : forçage > préemption (importance) > variété (cooldown catégorie) > cumul de
// priorité (stride). Ne renvoie jamais deux fois d'affilée le même message.
export function pickNext(providers, available, state) {
  if (state.forcedId && available.has(state.forcedId)) return state.forcedId;

  const urgent = providers
    .filter((p) => available.has(p.id) && impRank(p.importance) >= impRank('high') && p.id !== state.lastId)
    .sort((a, b) => impRank(b.importance) - impRank(a.importance) || b.priority - a.priority);
  if (urgent.length) return urgent[0].id;

  const recent = new Set(state.recent);
  const base = providers.filter((p) => available.has(p.id) && p.id !== state.lastId);
  let pool = base.filter((p) => !recent.has(p.category));
  if (!pool.length) pool = base;
  if (!pool.length) pool = providers.filter((p) => available.has(p.id));

  let best = null;
  let bestCredit = -Infinity;
  for (const p of pool) {
    const c = state.credits[p.id] || 0;
    if (c > bestCredit) { bestCredit = c; best = p; }
  }
  return best ? best.id : null;
}

// Ordonnanceur avec état interne (crédits stride + cooldown catégorie).
export function createScheduler(providers) {
  const credits = {};
  providers.forEach((p) => { credits[p.id] = 0; });
  let lastId = null;
  const recent = [];

  return {
    next(available, opts = {}) {
      const avail = available instanceof Set ? available : new Set(available);
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

// ── Helpers ────────────────────────────────────────────────────────────────

function formatJST(date) {
  return new Intl.DateTimeFormat('fr-FR', {
    timeZone: 'Asia/Tokyo', hour: '2-digit', minute: '2-digit', hour12: false,
  }).format(date);
}

function district(ctx) {
  if (!ctx.center) return null;
  return describeDistrict(ctx.center.lat, ctx.center.lon, ctx.zoom);
}

// ── Context providers (permanents) ─────────────────────────────────────────

function makeContextProviders() {
  return [
    {
      id: 'weather',
      build: (ctx) => (ctx.weather
        ? { icon: ctx.weather.emoji, main: `${ctx.weather.temp}°`, sub: ctx.weather.label }
        : null),
    },
    {
      id: 'time',
      build: (ctx) => ({ icon: '🕒', main: formatJST(ctx.now), sub: 'JST' }),
    },
    {
      id: 'district',
      build: (ctx) => {
        const r = district(ctx);
        return r ? { icon: r.natural.emoji, main: r.natural.text, sub: null } : null;
      },
    },
  ];
}

// ── Editorial providers (rotatifs — un seul bloc) ──────────────────────────

function makeEditorialProviders() {
  return [
    {
      id: 'ed-advice', category: 'advice', priority: 6, importance: 'normal',
      build: (ctx) => (ctx.weather ? { icon: ctx.weather.emoji, text: ctx.weather.message } : null),
    },
    {
      id: 'ed-discover', category: 'place', priority: 7, importance: 'normal',
      build: (ctx) => { const r = district(ctx); return r && r.tag ? { icon: r.tag.emoji, text: r.tag.text } : null; },
    },
    {
      id: 'ed-season', category: 'season', priority: 5, importance: 'low',
      build: () => { const s = seasonFor(todayJST()); return { icon: s.emoji, text: s.note }; },
    },
    {
      id: 'ed-events', category: 'events', priority: 4, importance: 'normal',
      build: (ctx) => {
        const n = ctx.events?.length || 0;
        return n > 0 ? { icon: '🎭', text: `${n} événement${n > 1 ? 's' : ''} à explorer sur la carte` } : null;
      },
    },
    {
      id: 'ed-fallback', category: 'fallback', priority: 0, importance: 'low',
      build: () => ({ icon: '✨', text: "Découvrez ce qui se passe à Tokyo aujourd'hui." }),
    },
  ];
}

// ── Moteur (effets de bord : DOM, carte, timers) ───────────────────────────

export function initTokyoLive() {
  const el = document.getElementById('tokyo-live');
  if (!el) return;

  const reduceMotion = typeof matchMedia === 'function'
    && matchMedia('(prefers-reduced-motion: reduce)').matches;

  const contextProviders = makeContextProviders();
  const editorialProviders = makeEditorialProviders();
  const scheduler = createScheduler(editorialProviders);
  let weather = null;
  let editorialCards = {};

  el.innerHTML =
    '<div class="tlive-context"></div>'
    + '<div class="tlive-editorial"><div class="tlive-card" role="status" aria-live="polite"></div></div>';
  el.hidden = false;

  const contextEl = el.querySelector('.tlive-context');
  const editorialEl = el.querySelector('.tlive-editorial');
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

  // ── Contexte permanent (jamais animé, mis à jour en place) ──
  function renderContext() {
    const ctx = buildCtx();
    contextEl.innerHTML = contextProviders.map((p) => {
      let b = null;
      try { b = p.build(ctx); } catch { b = null; }
      if (!b) return '';
      const sub = b.sub ? `<span class="tlive-b-sub">${escapeHtml(b.sub)}</span>` : '';
      return '<div class="tlive-block">'
        + `<span class="tlive-b-ico" aria-hidden="true">${b.icon}</span>`
        + `<span class="tlive-b-main">${escapeHtml(b.main)}</span>${sub}</div>`;
    }).join('');
  }

  // ── Bloc éditorial (seul élément animé) ──
  function editorialHTML(card) {
    return `<span class="tlive-ed-ico" aria-hidden="true">${card.icon}</span>`
      + `<span class="tlive-ed-text">${escapeHtml(card.text)}</span>`;
  }

  let swapTimer = null;
  function renderEditorial(card) {
    if (!card) return;
    const html = editorialHTML(card);
    if (reduceMotion) { cardEl.innerHTML = html; return; }
    clearTimeout(swapTimer);
    cardEl.classList.add('is-leaving');
    swapTimer = setTimeout(() => {
      cardEl.innerHTML = html;
      cardEl.classList.remove('is-leaving');
      cardEl.classList.add('is-entering');
      void cardEl.offsetWidth; // reflow → transition douce vers l'état normal
      cardEl.classList.remove('is-entering');
    }, ANIM_MS / 2);
  }

  function computeEditorialAvailable() {
    const ctx = buildCtx();
    editorialCards = {};
    const available = new Set();
    for (const p of editorialProviders) {
      let c = null;
      try { c = p.build(ctx) || null; } catch { c = null; }
      editorialCards[p.id] = c;
      if (c) available.add(p.id);
    }
    return available;
  }

  function advanceEditorial(opts = {}) {
    const available = computeEditorialAvailable();
    const id = scheduler.next(available, opts);
    if (id) renderEditorial(editorialCards[id]);
  }

  // ── Timers ──
  let rotTimer = null;
  let paused = false;
  function scheduleRot() { clearTimeout(rotTimer); rotTimer = setTimeout(tickRot, ROTATE_MS); }
  function tickRot() { if (!paused) advanceEditorial(); scheduleRot(); }
  function kickEditorial(opts) { advanceEditorial(opts); scheduleRot(); }

  setInterval(() => { if (!paused) renderContext(); }, CONTEXT_REFRESH_MS);

  // ── Interactions (seul le bloc éditorial réagit au clic/hover) ──
  editorialEl.addEventListener('mouseenter', () => { paused = true; clearTimeout(rotTimer); });
  editorialEl.addEventListener('mouseleave', () => { paused = false; scheduleRot(); });
  editorialEl.addEventListener('click', () => kickEditorial());
  if (typeof document.addEventListener === 'function') {
    document.addEventListener('visibilitychange', () => {
      if (document.hidden) { paused = true; clearTimeout(rotTimer); }
      else { paused = false; scheduleRot(); }
    });
  }

  // Déplacement de carte → le quartier permanent se met à jour (sans animation).
  if (map && typeof map.on === 'function') {
    let moveTimer = null;
    map.on('moveend', () => {
      clearTimeout(moveTimer);
      moveTimer = setTimeout(renderContext, MOVE_DEBOUNCE_MS);
    });
  }

  // ── Météo (asynchrone) ──
  fetchWeather().then((w) => {
    if (!w) return;
    weather = w;
    renderContext();      // la météo apparaît dans le contexte permanent
    kickEditorial();      // le conseil météo devient disponible en rotation
  });
  setInterval(() => {
    fetchWeather().then((w) => { if (w) { weather = w; renderContext(); } });
  }, WEATHER_REFRESH_MS);

  // ── Premier rendu ──
  renderContext();
  advanceEditorial();
  scheduleRot();
}
