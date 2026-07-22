import { describe, test, expect, beforeEach, afterEach, vi } from 'vitest';
import { pickNext, createScheduler, initTokyoLive } from '../js/tokyo-live.js';
import { seasonFor, describeDistrict, nearestDistrict, SEASONAL_CARDS, inSeasonWindow } from '../js/tokyo-live-data.js';
import { fetchWeather } from '../js/weather.js';

// ── Ordonnanceur ────────────────────────────────────────────────────────────

const PROVIDERS = [
  { id: 'weather', category: 'weather', priority: 10, importance: 'normal' },
  { id: 'time',    category: 'time',    priority: 8,  importance: 'normal' },
  { id: 'season',  category: 'season',  priority: 3,  importance: 'low' },
];

describe('createScheduler', () => {
  test('ne répète jamais deux fois la même carte d\'affilée', () => {
    const s = createScheduler(PROVIDERS);
    const all = new Set(['weather', 'time', 'season']);
    let prev = null;
    for (let i = 0; i < 200; i++) {
      const id = s.next(all);
      expect(id).not.toBe(prev);
      prev = id;
    }
  });

  test('les hautes priorités apparaissent plus souvent (jeu nominal)', () => {
    // Avec assez de providers (comme en conditions réelles), le cooldown de catégorie
    // n'impose plus un round-robin strict : la priorité départage réellement.
    const p5 = [
      { id: 'weather', category: 'weather', priority: 10, importance: 'normal' },
      { id: 'time',    category: 'time',    priority: 8,  importance: 'normal' },
      { id: 'sun',     category: 'sun',     priority: 6,  importance: 'low' },
      { id: 'season',  category: 'season',  priority: 3,  importance: 'low' },
      { id: 'place',   category: 'place',   priority: 2,  importance: 'normal' },
    ];
    const s = createScheduler(p5);
    const all = new Set(p5.map((p) => p.id));
    const count = Object.fromEntries(p5.map((p) => [p.id, 0]));
    for (let i = 0; i < 1000; i++) count[s.next(all)]++;
    expect(count.weather).toBeGreaterThan(count.season);
    expect(count.time).toBeGreaterThan(count.season);
    expect(count.weather).toBeGreaterThan(count.place);
  });

  test('exclut les providers dont la carte est indisponible', () => {
    const s = createScheduler(PROVIDERS);
    const onlyTime = new Set(['time']);
    for (let i = 0; i < 20; i++) expect(s.next(onlyTime)).toBe('time');
  });
});

describe('pickNext', () => {
  const state = () => ({ credits: {}, recent: [], lastId: null, forcedId: undefined });

  test('le forçage gagne quand la carte est disponible', () => {
    const st = state(); st.forcedId = 'season';
    expect(pickNext(PROVIDERS, new Set(['weather', 'time', 'season']), st)).toBe('season');
  });

  test('un forçage indisponible est ignoré', () => {
    const st = state(); st.forcedId = 'season';
    const id = pickNext(PROVIDERS, new Set(['weather', 'time']), st);
    expect(id).not.toBe('season');
  });

  test('une carte critique préempte la rotation normale', () => {
    const providers = [
      ...PROVIDERS,
      { id: 'alert', category: 'alert', priority: 1, importance: 'critical' },
    ];
    const id = pickNext(providers, new Set(['weather', 'time', 'alert']), state());
    expect(id).toBe('alert');
  });

  test('le fallback est choisi quand il est seul disponible', () => {
    const providers = [...PROVIDERS, { id: 'fallback', category: 'fallback', priority: 0, importance: 'low' }];
    expect(pickNext(providers, new Set(['fallback']), state())).toBe('fallback');
  });

  test('la catégorie récente est évitée si une alternative existe', () => {
    const st = state(); st.recent = ['weather']; st.credits = { weather: 100, time: 1, season: 1 };
    // weather a le plus gros crédit mais est en cooldown → on prend un autre
    expect(pickNext(PROVIDERS, new Set(['weather', 'time', 'season']), st)).not.toBe('weather');
  });
});

// ── Saisons ──────────────────────────────────────────────────────────────────

describe('seasonFor', () => {
  const on = (m, d) => seasonFor(new Date(Date.UTC(2026, m - 1, d)));

  test.each([
    [1, 15, 'Hiver'],
    [3, 19, 'Hiver'],
    [3, 20, 'Cerisiers en fleurs'],
    [4, 10, 'Cerisiers en fleurs'],
    [4, 11, 'Nouvelle verdure'],
    [6, 15, 'Saison des pluies'],
    [8, 1, "Feux d'artifice"],
    [10, 1, 'Automne'],
    [11, 15, "Érables d'automne"],
    [12, 25, 'Illuminations'],
  ])('%i/%i → %s', (m, d, label) => {
    expect(on(m, d).label).toBe(label);
  });
});

// ── Quartiers ────────────────────────────────────────────────────────────────

describe('nearestDistrict', () => {
  test('trouve le quartier le plus proche', () => {
    const { district } = nearestDistrict(35.6595, 139.7005); // Shibuya exact
    expect(district.name).toBe('Shibuya');
  });
});

describe('describeDistrict', () => {
  test('vue trop large (zoom < 12) → null', () => {
    expect(describeDistrict(35.6595, 139.7005, 10)).toBeNull();
  });

  test('point trop loin de tout quartier → null', () => {
    expect(describeDistrict(34.6937, 135.5023, 14)).toBeNull(); // Osaka
  });

  test('centré sur un quartier → "Exploration de …"', () => {
    const r = describeDistrict(35.6595, 139.7005, 14); // Shibuya
    expect(r.name).toBe('Shibuya');
    expect(r.natural.text).toBe('Exploration de Shibuya');
  });

  test('un peu décentré → "Autour de …"', () => {
    // ~1.4 km au sud d'Odaiba (quartier isolé → pas d'ambiguïté de voisinage)
    const r = describeDistrict(35.6170, 139.7752, 14);
    expect(r.name).toBe('Odaiba');
    expect(r.natural.text.startsWith('Autour de')).toBe(true);
  });

  test('quartier tagué → carte éditoriale disponible', () => {
    const r = describeDistrict(35.7141, 139.7774, 14); // Ueno
    expect(r.tag).not.toBeNull();
    expect(r.tag.text).toContain('Ueno');
  });
});

// ── Temps forts saisonniers (gated par période) ──────────────────────────────

describe('inSeasonWindow', () => {
  const on = (m, d) => new Date(Date.UTC(2026, m - 1, d));

  test('carte active dans sa fenêtre', () => {
    const sakura = SEASONAL_CARDS.find((c) => c.id === 'sakura-start');
    expect(inSeasonWindow(sakura, on(3, 25))).toBe(true);
  });

  test('carte inactive hors fenêtre', () => {
    const sakura = SEASONAL_CARDS.find((c) => c.id === 'sakura-start');
    expect(inSeasonWindow(sakura, on(6, 1))).toBe(false);
  });

  test('bornes incluses', () => {
    const hanabi = SEASONAL_CARDS.find((c) => c.id === 'hanabi');
    expect(inSeasonWindow(hanabi, on(7, 21))).toBe(true);
    expect(inSeasonWindow(hanabi, on(8, 20))).toBe(true);
    expect(inSeasonWindow(hanabi, on(8, 21))).toBe(false);
  });
});

// ── Montage (smoke test du moteur avec un DOM minimal) ───────────────────────

// Faux nœud DOM : suffisant pour exercer le rendu par nœuds + le responsive.
function fakeEl() {
  const self = {
    innerHTML: '', hidden: true, className: '', dataset: {}, style: {},
    children: [], parentNode: null,
    offsetWidth: 0, scrollWidth: 0, clientWidth: 1000, _q: {},
    classList: { _s: new Set(), add(c) { this._s.add(c); }, remove(c) { this._s.delete(c); }, contains(c) { return this._s.has(c); } },
    addEventListener() {},
    appendChild(child) {
      const i = self.children.indexOf(child);
      if (i >= 0) self.children.splice(i, 1);
      self.children.push(child); child.parentNode = self; return child;
    },
    remove() {
      const p = self.parentNode;
      if (p) { const i = p.children.indexOf(self); if (i >= 0) p.children.splice(i, 1); }
      self.parentNode = null;
    },
    querySelector(sel) { self._q[sel] = self._q[sel] || fakeEl(); return self._q[sel]; },
  };
  return self;
}

describe('initTokyoLive (montage)', () => {
  let host;
  beforeEach(() => {
    vi.useFakeTimers();
    host = fakeEl();
    vi.stubGlobal('document', {
      getElementById: (id) => (id === 'tokyo-live' ? host : null),
      createElement: () => fakeEl(),
      addEventListener() {},
      hidden: false,
    });
    vi.stubGlobal('matchMedia', () => ({ matches: true })); // reduce-motion → rendu synchrone
    vi.stubGlobal('fetch', vi.fn(async () => { throw new Error('offline'); }));
  });
  afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers(); });

  test('monte la barre (contexte + éditorial) sans lever d\'erreur', () => {
    expect(() => initTokyoLive()).not.toThrow();
    expect(host.hidden).toBe(false);
    // Contexte permanent : heure + saison + quartier « Tokyo » présents même hors réseau.
    const blocks = host.querySelector('.tlive-context').children;
    expect(blocks.length).toBeGreaterThan(0);
    expect(blocks.some((b) => b.innerHTML.includes('tlive-b-main'))).toBe(true);
    // Bloc éditorial : le vibe horaire garantit un contenu même sans météo/événements.
    expect(host.querySelector('.tlive-card').innerHTML).toContain('tlive-ed-text');
  });
});

// ── fetchWeather ──────────────────────────────────────────────────────────────

describe('fetchWeather', () => {
  afterEach(() => vi.unstubAllGlobals());

  test('normalise le payload Open-Meteo (daily en tableaux + uvMax)', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: true,
      json: async () => ({
        current: { temperature_2m: 22.6, apparent_temperature: 25.4, relative_humidity_2m: 61, wind_speed_10m: 14.3, weather_code: 0 },
        hourly: { time: [], precipitation_probability: [] },
        daily: {
          sunrise: ['2026-07-20T04:39', '2026-07-21T04:40'],
          sunset: ['2026-07-20T18:56', '2026-07-21T18:55'],
          uv_index_max: [9.2, 8.1],
        },
      }),
    })));
    const w = await fetchWeather();
    expect(w.temp).toBe(23);
    expect(w.feels).toBe(25);
    expect(w.humidity).toBe(61);
    expect(w.wind).toBe(14);
    expect(w.emoji).toBe('☀️');
    expect(w.daily.sunrise[0]).toBe('2026-07-20T04:39');
    expect(w.daily.sunrise[1]).toBe('2026-07-21T04:40'); // demain
    expect(w.daily.sunset[0]).toBe('2026-07-20T18:56');
    expect(w.daily.uvMax).toBe(9.2);
    expect(typeof w.message).toBe('string');
  });

  test('renvoie null si les données sont incomplètes', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => ({ current: {} }) })));
    expect(await fetchWeather()).toBeNull();
  });

  test('renvoie null en cas d\'échec réseau', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => { throw new Error('offline'); }));
    expect(await fetchWeather()).toBeNull();
  });
});
