// ══════════════════════════════════════════════════════════════════════════
// Tokyo — « Context Bar » de l'en-tête.
//
// Barre de contexte qui occupe l'espace disponible du header. Deux familles :
//
//   • Context providers  → blocs permanents (météo, ressenti, heure, soleil,
//                          saison, quartier, événements). Rangés par PRIORITÉ :
//                          plus l'écran est large, plus on en affiche ; quand la
//                          place manque, on retire les moins prioritaires (à droite).
//                          Chaque bloc s'anime à l'apparition et lors d'un changement
//                          de valeur → la barre vit sans jamais s'agiter.
//   • Editorial providers → un seul bloc rotatif à droite (flex: 1) : messages
//                          factuels + éditoriaux, personnalisés selon le moment.
//
// EXTENSIBLE : ajouter une info = enregistrer un provider (context ou editorial),
// sans toucher au moteur.
//
// Contrat d'un provider :
//   context  : { id, rank, build(ctx) -> { icon, main, sub? } | null }   // rank = priorité
//   editorial: { id, category, priority, importance, build(ctx) -> { icon, text } | null }
//   ctx = { weather, now, center, zoom, events }
// ══════════════════════════════════════════════════════════════════════════
import { map, allEvents } from './state.js';
import { escapeHtml, todayJST } from './utils.js';
import { fetchWeather } from './weather.js';
import { seasonFor, describeDistrict, SEASONAL_CARDS, inSeasonWindow } from './tokyo-live-data.js';

const SECOND = 1000;
const MINUTE = 60 * SECOND;

const ROTATE_MS = 12 * SECOND;          // rotation du bloc éditorial (10–15 s)
const ANIM_MS = 300;                    // transition quasi invisible (fondu + slide)
const CONTEXT_REFRESH_MS = 15 * SECOND; // rafraîchissement du contexte (surtout l'heure)
const MOVE_DEBOUNCE_MS = 300;           // anti-spam sur les déplacements de carte
const WEATHER_REFRESH_MS = 30 * MINUTE;
const RECENT_WINDOW = 2;                // cooldown par catégorie (éditorial)
const EDITORIAL_MIN_PX = 150;           // largeur mini réservée au bloc éditorial

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

function weekdayJST(date) {
  return new Intl.DateTimeFormat('en-US', { timeZone: 'Asia/Tokyo', weekday: 'short' }).format(date);
}

function district(ctx) {
  if (!ctx.center) return null;
  return describeDistrict(ctx.center.lat, ctx.center.lon, ctx.zoom);
}

// Minutes écoulées depuis minuit, en heure de Tokyo.
function minutesJST(date) {
  const [h, m] = formatJST(date).split(':').map(Number);
  return h * 60 + m;
}
const jstHour = (date) => Math.floor(minutesJST(date) / 60);
// "2026-07-20T18:56" → minutes depuis minuit (589) ; null si absent
const isoToMin = (iso) => (iso ? Number(iso.slice(11, 13)) * 60 + Number(iso.slice(14, 16)) : null);

// Durée courte lisible : 42 → "42 min", 80 → "1 h 20"
function fmtDuration(min) {
  if (min < 60) return `${min} min`;
  return `${Math.floor(min / 60)} h ${String(min % 60).padStart(2, '0')}`;
}

// Première heure À VENIR aujourd'hui avec forte probabilité de pluie → "18:00" (factuel).
function upcomingRainHour(hourly, nowHour) {
  if (!hourly?.time) return null;
  const today = hourly.time[0]?.slice(0, 10);
  for (let i = 0; i < hourly.time.length; i++) {
    const iso = hourly.time[i];
    if (iso.slice(0, 10) !== today) break;                 // on se limite à aujourd'hui
    if (Number(iso.slice(11, 13)) <= nowHour) continue;    // uniquement à venir
    if ((hourly.precipitation_probability?.[i] ?? 0) >= 60) return iso.slice(11, 16);
  }
  return null;
}

const isRainingNow = (c) => (c >= 51 && c <= 67) || (c >= 80 && c <= 82) || c >= 95;

// Bloc permanent « soleil » : affiche toujours le prochain événement solaire pertinent.
//   • dans les 3 h avant le coucher  → compte à rebours « 🌇 dans 42 min · coucher »
//   • petit matin (avant le lever)   → « 🌅 04:40 · lever »
//   • soir (après le coucher)        → lever de demain « 🌅 04:41 · lever demain »
//   • journée                        → coucher du jour « 🌇 18:56 · coucher »
// Renvoie null tant que la météo n'est pas chargée (le bloc est alors simplement masqué).
function buildSunContext(ctx) {
  const d = ctx.weather?.daily;
  if (!d) return null;
  const nowM = minutesJST(ctx.now);
  const set0 = d.sunset?.[0];
  const rise0 = d.sunrise?.[0];
  if (set0) {
    const diff = isoToMin(set0) - nowM;
    if (diff > 0 && diff <= 180) return { icon: '🌇', main: `dans ${fmtDuration(diff)}`, sub: 'coucher' };
  }
  if (rise0 && nowM < isoToMin(rise0)) return { icon: '🌅', main: rise0.slice(11, 16), sub: 'lever' };
  if (set0 && nowM >= isoToMin(set0) && d.sunrise?.[1]) {
    return { icon: '🌅', main: d.sunrise[1].slice(11, 16), sub: 'lever demain' };
  }
  if (set0) return { icon: '🌇', main: set0.slice(11, 16), sub: 'coucher' };
  return null;
}

// Message éditorial « d'ambiance » selon l'heure de Tokyo (toujours disponible → floor).
function timeVibe(ctx) {
  const h = jstHour(ctx.now);
  if (h < 5) return { icon: '🌙', text: 'Tokyo ne dort jamais' };
  if (h < 9) return { icon: '🌅', text: 'Tokyo s’éveille doucement' };
  if (h < 11) return { icon: '☕', text: 'Matinée tranquille à Tokyo' };
  if (h < 14) return { icon: '🍜', text: 'C’est l’heure du déjeuner à Tokyo' };
  if (h < 17) return { icon: '🚶', text: 'Bel après-midi pour explorer' };
  if (h < 19) return { icon: '🌇', text: 'Tokyo se pare de lumières' };
  if (h < 22) return { icon: '🏮', text: 'Tokyo s’illumine' };
  return { icon: '🌃', text: 'Douceur nocturne à Tokyo' };
}

// ── Context providers (permanents, rangés par priorité) ────────────────────
// rank croissant = priorité décroissante ; on retire les plus grands rank d'abord.

function makeContextProviders() {
  return [
    {
      id: 'weather', rank: 1,
      build: (ctx) => (ctx.weather
        ? { icon: ctx.weather.emoji, main: `${ctx.weather.temp}°`, sub: ctx.weather.label }
        : null),
    },
    {
      id: 'time', rank: 2,
      build: (ctx) => ({ icon: '🕒', main: formatJST(ctx.now), sub: 'JST' }),
    },
    {
      id: 'district', rank: 3,
      // Toujours présent : dézoomé / hors zone → vue d'ensemble « Tokyo ».
      build: (ctx) => {
        const r = district(ctx);
        if (r) return { icon: r.natural.emoji, main: r.natural.text, sub: null };
        return { icon: '📍', main: 'Tokyo', sub: null };
      },
    },
    {
      id: 'season', rank: 4,
      // Libellé français clair, sans terme japonais dans le bloc permanent.
      build: () => { const s = seasonFor(todayJST()); return { icon: s.emoji, main: s.label, sub: 'saison' }; },
    },
    {
      id: 'sun', rank: 5,
      build: buildSunContext,
    },
    {
      id: 'events', rank: 6,
      build: (ctx) => {
        const n = ctx.events?.length || 0;
        return n > 0 ? { icon: '🎭', main: `${n} événement${n > 1 ? 's' : ''}`, sub: null } : null;
      },
    },
    {
      id: 'feels', rank: 7,
      build: (ctx) => (ctx.weather && ctx.weather.feels != null
        ? { icon: '🌡️', main: `${ctx.weather.feels}°`, sub: 'ressenti' }
        : null),
    },
    {
      id: 'humidity', rank: 8,
      build: (ctx) => (ctx.weather && ctx.weather.humidity != null
        ? { icon: '💧', main: `${ctx.weather.humidity}%`, sub: 'humidité' }
        : null),
    },
    {
      id: 'wind', rank: 9,
      build: (ctx) => (ctx.weather && ctx.weather.wind != null
        ? { icon: '💨', main: `${ctx.weather.wind} km/h`, sub: 'vent' }
        : null),
    },
  ];
}

// ── Editorial providers (rotatifs — un seul bloc) ──────────────────────────
//
// Principe : une carte n'apparaît QUE si elle porte une info réelle et pertinente
// (build → null sinon). La fréquence contextuelle en découle mécaniquement : une carte
// n'est éligible que dans sa fenêtre (pluie imminente, période saisonnière réelle…),
// et sa `priority` la favorise à ce moment-là. Le floor est un message d'ambiance
// (vrai selon l'heure), jamais une fausse info.

function makeEditorialProviders() {
  const providers = [
    // ── Météo factuelle (dérivée des données Open-Meteo) ──
    {
      id: 'wx-rain-now', category: 'weather', priority: 9, importance: 'normal',
      build: (ctx) => (ctx.weather && isRainingNow(ctx.weather.code)
        ? { icon: '🌧️', text: 'Il pleut en ce moment — pensez au parapluie' } : null),
    },
    {
      id: 'wx-rain-soon', category: 'weather', priority: 9, importance: 'normal',
      build: (ctx) => {
        if (!ctx.weather) return null;
        const h = upcomingRainHour(ctx.weather.hourly, jstHour(ctx.now));
        return h ? { icon: '☔', text: `Pluie attendue vers ${h}` } : null;
      },
    },
    {
      id: 'wx-uv', category: 'weather', priority: 7, importance: 'normal',
      build: (ctx) => (ctx.weather?.daily?.uvMax >= 8
        ? { icon: '💧', text: 'Indice UV élevé aujourd’hui — hydratez-vous' } : null),
    },
    {
      id: 'wx-hot', category: 'weather', priority: 6, importance: 'normal',
      build: (ctx) => (ctx.weather && ctx.weather.temp >= 33
        ? { icon: '🥵', text: `${ctx.weather.temp}° — forte chaleur, hydratez-vous` } : null),
    },
    {
      id: 'wx-cold', category: 'weather', priority: 6, importance: 'normal',
      build: (ctx) => (ctx.weather && ctx.weather.temp <= 2
        ? { icon: '🧣', text: `${ctx.weather.temp}° — couvrez-vous bien` } : null),
    },

    // ── Lieu éditorial (tag du quartier exploré) ──
    {
      id: 'place-discover', category: 'place', priority: 6, importance: 'normal',
      build: (ctx) => { const r = district(ctx); return r && r.tag ? { icon: r.tag.emoji, text: r.tag.text } : null; },
    },

    // ── Week-end (personnalisé selon le jour) ──
    {
      id: 'weekend', category: 'vibe', priority: 3, importance: 'low',
      build: (ctx) => {
        const wd = weekdayJST(ctx.now);
        return (wd === 'Sat' || wd === 'Sun') ? { icon: '🎉', text: 'C’est le week-end à Tokyo' } : null;
      },
    },

    // ── Ambiance selon l'heure (floor : toujours disponible) ──
    { id: 'vibe', category: 'vibe', priority: 2, importance: 'low', build: timeVibe },
  ];

  // ── Temps forts saisonniers : un provider gated par période (et parfois par lieu) ──
  for (const c of SEASONAL_CARDS) {
    providers.push({
      id: `season-${c.id}`, category: 'season', priority: c.near ? 9 : 8, importance: 'low',
      build: (ctx) => {
        if (!inSeasonWindow(c, todayJST())) return null;
        if (c.near) { const r = district(ctx); if (!r || r.name !== c.near) return null; }
        return { icon: c.emoji, text: c.text };
      },
    });
  }

  return providers;
}

// ── Moteur (effets de bord : DOM, carte, timers) ───────────────────────────

export function initTokyoLive() {
  const el = document.getElementById('tokyo-live');
  if (!el) return;

  const reduceMotion = typeof matchMedia === 'function'
    && matchMedia('(prefers-reduced-motion: reduce)').matches;
  const raf = typeof requestAnimationFrame === 'function' ? requestAnimationFrame : (fn) => fn();

  const contextProviders = makeContextProviders();
  const editorialProviders = makeEditorialProviders();
  const scheduler = createScheduler(editorialProviders);
  let weather = null;
  let editorialCards = {};
  const blockEls = {}; // id -> { el, sig }

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

  // ── Contexte permanent : rendu par nœuds (diff par widget → animations) ──
  function blockInner(b) {
    const sub = b.sub ? `<span class="tlive-b-sub">${escapeHtml(b.sub)}</span>` : '';
    return `<span class="tlive-b-ico" aria-hidden="true">${b.icon}</span>`
      + `<span class="tlive-b-main">${escapeHtml(b.main)}</span>${sub}`;
  }

  function flashUpdate(blockEl) {
    const mainEl = blockEl.querySelector('.tlive-b-main');
    if (!mainEl || !mainEl.classList) return;
    mainEl.classList.remove('is-updated');
    void blockEl.offsetWidth;              // reflow → l'animation peut rejouer
    mainEl.classList.add('is-updated');
  }

  function renderContext() {
    const ctx = buildCtx();
    contextProviders.forEach((p, i) => {
      let b = null;
      try { b = p.build(ctx); } catch { b = null; }
      const cur = blockEls[p.id];
      if (!b) {
        if (cur) { cur.el.remove(); delete blockEls[p.id]; }
        return;
      }
      const sig = `${b.icon}|${b.main}|${b.sub || ''}`;
      if (!cur) {
        const bl = document.createElement('div');
        bl.className = 'tlive-block';
        bl.innerHTML = blockInner(b);
        if (!reduceMotion) {
          bl.classList.add('is-enter');
          bl.style.transitionDelay = `${Math.min(i, 8) * 40}ms`;   // apparition en cascade
          raf(() => raf(() => { bl.classList.remove('is-enter'); bl.style.transitionDelay = ''; }));
        }
        contextEl.appendChild(bl);
        blockEls[p.id] = { el: bl, sig };
      } else {
        contextEl.appendChild(cur.el);      // ré-ordonne selon la priorité (rank)
        if (cur.sig !== sig) {
          cur.el.innerHTML = blockInner(b);
          cur.sig = sig;
          if (!reduceMotion) flashUpdate(cur.el);
        }
      }
    });
    fitContext();
  }

  // ── Responsive : montre tout, puis retire les blocs de plus faible priorité ──
  function fitContext() {
    const blocks = [...contextEl.children];
    blocks.forEach((bl) => { bl.style.display = ''; });
    for (let i = blocks.length - 1; i >= 1; i--) {          // garde toujours le 1er (météo)
      const overflow = el.scrollWidth > el.clientWidth + 1;
      const tight = (el.clientWidth - contextEl.offsetWidth) < EDITORIAL_MIN_PX;
      if (!overflow && !tight) break;
      blocks[i].style.display = 'none';
    }
  }

  // ── Bloc éditorial (rotatif, animé) ──
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
      void cardEl.offsetWidth;
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

  // ── Responsive : recalcule le nombre de blocs quand la largeur change ──
  if (typeof ResizeObserver === 'function') {
    new ResizeObserver(() => fitContext()).observe(el);
  }

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

  // Déplacement de carte → le quartier se met à jour (avec un flash discret).
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
    renderContext();      // météo + ressenti + soleil apparaissent (en cascade)
    kickEditorial();      // les cartes météo deviennent disponibles en rotation
  });
  setInterval(() => {
    fetchWeather().then((w) => { if (w) { weather = w; renderContext(); } });
  }, WEATHER_REFRESH_MS);

  // ── Premier rendu ──
  renderContext();
  advanceEditorial();
  scheduleRot();
}
