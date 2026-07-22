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

// ── Cellules de contexte (permanentes) ─────────────────────────────────────
// Chaque cellule appartient à un `group` (regroupement visuel : les cellules d'un
// même groupe sont collées, un séparateur ne s'affiche qu'ENTRE groupes) et porte un
// `rank` = priorité (indépendante de la position). Quand la place manque, on masque
// les rangs les plus élevés d'abord — donc les détails météo (ressenti, humidité,
// vent) disparaissent avant l'heure, même s'ils sont affichés à gauche avec la météo.
//   detail:true → cellule secondaire (grisée, préfixée d'un « · »), sans icône.

const GROUP_ORDER = ['weather', 'time', 'place', 'events', 'sun', 'season'];

function makeContextCells() {
  return [
    // ── Groupe météo (tout ce qui touche au temps, regroupé) ──
    {
      id: 'temp', group: 'weather', rank: 1,
      build: (ctx) => (ctx.weather ? { icon: ctx.weather.emoji, main: `${ctx.weather.temp}°`, sub: ctx.weather.label } : null),
    },
    {
      id: 'feels', group: 'weather', rank: 4, detail: true,
      build: (ctx) => (ctx.weather && ctx.weather.feels != null ? { main: `ressenti ${ctx.weather.feels}°` } : null),
    },
    {
      id: 'humidity', group: 'weather', rank: 8, detail: true,
      build: (ctx) => (ctx.weather && ctx.weather.humidity != null ? { main: `${ctx.weather.humidity}%` } : null),
    },
    {
      id: 'wind', group: 'weather', rank: 9, detail: true,
      build: (ctx) => (ctx.weather && ctx.weather.wind != null ? { main: `${ctx.weather.wind} km/h` } : null),
    },

    // ── Heure ──
    { id: 'time', group: 'time', rank: 2, build: (ctx) => ({ icon: '🕒', main: formatJST(ctx.now), sub: 'JST' }) },

    // ── Quartier (toujours présent : dézoomé / hors zone → « Tokyo ») ──
    {
      id: 'district', group: 'place', rank: 3,
      build: (ctx) => { const r = district(ctx); return r ? { icon: r.natural.emoji, main: r.natural.text } : { icon: '📍', main: 'Tokyo' }; },
    },

    // ── Événements chargés sur la carte ──
    {
      id: 'events', group: 'events', rank: 5,
      build: (ctx) => { const n = ctx.events?.length || 0; return n > 0 ? { icon: '🎭', main: `${n} événement${n > 1 ? 's' : ''}` } : null; },
    },

    // ── Soleil (prochain événement solaire) ──
    { id: 'sun', group: 'sun', rank: 6, build: buildSunContext },

    // ── Saison (libellé français clair) ──
    { id: 'season', group: 'season', rank: 7, build: () => { const s = seasonFor(todayJST()); return { icon: s.emoji, main: s.label }; } },
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

  const contextCells = makeContextCells();
  const editorialProviders = makeEditorialProviders();
  const scheduler = createScheduler(editorialProviders);
  let weather = null;
  let editorialCards = {};
  const cellState = {};  // id -> { el, sig }
  const groupState = {}; // group -> element

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

  // ── Contexte permanent : groupes + cellules (diff par cellule → animations) ──
  function cellInner(b) {
    const ico = b.icon ? `<span class="tlive-c-ico" aria-hidden="true">${b.icon}</span>` : '';
    const sub = b.sub ? `<span class="tlive-c-sub">${escapeHtml(b.sub)}</span>` : '';
    return `${ico}<span class="tlive-c-main">${escapeHtml(b.main)}</span>${sub}`;
  }

  function flashUpdate(cellEl) {
    const mainEl = cellEl.querySelector('.tlive-c-main');
    if (!mainEl || !mainEl.classList) return;
    mainEl.classList.remove('is-updated');
    void cellEl.offsetWidth;              // reflow → l'animation peut rejouer
    mainEl.classList.add('is-updated');
  }

  function ensureGroup(name) {
    if (!groupState[name]) {
      const g = document.createElement('div');
      g.className = 'tlive-group';
      groupState[name] = g;
    }
    return groupState[name];
  }

  function renderContext() {
    const ctx = buildCtx();
    contextCells.forEach((def, i) => {
      let b = null;
      try { b = def.build(ctx); } catch { b = null; }
      const cur = cellState[def.id];
      if (!b || b.main == null) {
        if (cur) { cur.el.remove(); delete cellState[def.id]; }
        return;
      }
      const sig = `${b.icon || ''}|${b.main}|${b.sub || ''}`;
      const group = ensureGroup(def.group);
      if (!cur) {
        const cell = document.createElement('div');
        cell.className = 'tlive-cell' + (def.detail ? ' tlive-cell--detail' : '');
        cell.dataset.rank = String(def.rank);
        cell.innerHTML = cellInner(b);
        if (!reduceMotion) {
          cell.classList.add('is-enter');
          cell.style.transitionDelay = `${Math.min(i, 8) * 40}ms`;   // apparition en cascade
          raf(() => raf(() => { cell.classList.remove('is-enter'); cell.style.transitionDelay = ''; }));
        }
        group.appendChild(cell);
        cellState[def.id] = { el: cell, sig };
      } else {
        group.appendChild(cur.el);          // ré-ordonne la cellule dans son groupe
        if (cur.sig !== sig) {
          cur.el.innerHTML = cellInner(b);
          cur.sig = sig;
          if (!reduceMotion) flashUpdate(cur.el);
        }
      }
    });
    // (ré)insère les groupes non vides dans l'ordre défini
    for (const name of GROUP_ORDER) {
      const g = groupState[name];
      if (g && g.children.length) contextEl.appendChild(g);
    }
    fitContext();
  }

  // ── Responsive : masque les cellules par priorité (rang) jusqu'à ce que ça tienne.
  // Le rang est indépendant de la position → les détails météo (rangs élevés) partent
  // avant l'heure/le quartier, tout en restant visuellement collés à la météo. ──
  function fitContext() {
    const cells = Object.values(cellState);
    cells.forEach((c) => { c.el.style.display = ''; });
    Object.values(groupState).forEach((g) => { g.style.display = ''; });
    // rang décroissant : on cache le moins prioritaire d'abord
    const ordered = cells.slice().sort((a, b) => Number(b.el.dataset.rank) - Number(a.el.dataset.rank));
    for (const c of ordered) {
      if (el.scrollWidth <= el.clientWidth + 1) break;
      if (Number(c.el.dataset.rank) <= 1) continue;          // ne jamais masquer la météo
      c.el.style.display = 'none';
    }
    // masque les groupes dont toutes les cellules sont cachées (évite un séparateur orphelin)
    for (const g of Object.values(groupState)) {
      const kids = [...g.children];
      const anyVisible = kids.some((k) => k.style.display !== 'none');
      g.style.display = kids.length && anyVisible ? '' : 'none';
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
