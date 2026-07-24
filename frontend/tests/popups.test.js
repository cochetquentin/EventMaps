import { describe, test, expect, vi, beforeEach } from 'vitest';

vi.mock('../js/favorites.js', () => ({
  isFavorite: vi.fn().mockReturnValue(false),
}));
vi.mock('../js/config.js', () => ({
  iconTC: null,
  iconHanabi: null,
  iconUser: null,
  TC_EXCLUDED_CATS: [],
  CAT_EMOJI: {},
}));

import { buildPopup } from '../js/popups.js';
import { isFavorite } from '../js/favorites.js';

const BASE_TC = {
  id: 'tc-1',
  source: 'tc',
  title: 'Test Event',
  start_date: '2026-06-10',
  url: 'https://example.com',
  times: null,
  attributes: {},
  price: null,
  latitude: null,
  longitude: null,
};

const BASE_HANABI = {
  id: 'h-1',
  source: 'hanabi',
  title: 'Sumida Fireworks',
  start_date: '2026-07-25',
  url: 'https://hanabi.example.com',
  times: '19:00-21:00',
  attributes: {},
  venue: null,
  latitude: null,
  longitude: null,
};

describe('buildPopup — source tc', () => {
  beforeEach(() => {
    vi.mocked(isFavorite).mockReturnValue(false);
  });

  test('returns string containing event title', () => {
    expect(buildPopup(BASE_TC)).toContain('Test Event');
  });

  test('contains Tokyo Cheapo source badge', () => {
    expect(buildPopup(BASE_TC)).toContain('Tokyo Cheapo');
  });

  test('XSS: title with <script> is escaped', () => {
    const html = buildPopup({ ...BASE_TC, title: '<script>xss</script>' });
    expect(html).toContain('&lt;script&gt;');
    expect(html).not.toContain('<script>');
  });

  test('safe https:// URL rendered in href', () => {
    expect(buildPopup(BASE_TC)).toContain('href="https://example.com"');
  });

  test('javascript: URL replaced by href="#"', () => {
    const html = buildPopup({ ...BASE_TC, url: 'javascript:alert(1)' });
    expect(html).toContain('href="#"');
    expect(html).not.toContain('javascript:');
  });

  test('favorite button inactive (☆) when isFavorite=false', () => {
    const html = buildPopup(BASE_TC);
    expect(html).toContain('☆');
    expect(html).not.toContain('fav-btn pop-fav-btn active');
  });

  test('favorite button active (★) when isFavorite=true', () => {
    vi.mocked(isFavorite).mockReturnValue(true);
    const html = buildPopup(BASE_TC);
    expect(html).toContain('★');
    expect(html).toContain('fav-btn pop-fav-btn active');
  });

  test('price badge rendered when price is set', () => {
    const html = buildPopup({ ...BASE_TC, price: '¥1000' });
    expect(html).toContain('pop-badge');
    expect(html).toContain('¥1000');
  });

  test('no price badge when price is null', () => {
    expect(buildPopup(BASE_TC)).not.toContain('pop-badge');
  });

  test('directions links absent when no lat/lng', () => {
    const html = buildPopup(BASE_TC);
    expect(html).not.toContain('google.com/maps');
    expect(html).not.toContain('maps.apple.com');
  });

  test('Google Maps and Apple Maps links present when lat/lng set', () => {
    const html = buildPopup({ ...BASE_TC, latitude: 35.681, longitude: 139.767 });
    expect(html).toContain('google.com/maps/dir');
    expect(html).toContain('maps.apple.com');
  });

  test('ICS calendar link points to /events/tc-1.ics', () => {
    expect(buildPopup(BASE_TC)).toContain('/events/tc-1.ics');
  });

  test('time displayed when times is set', () => {
    const html = buildPopup({ ...BASE_TC, times: '14:00-16:00' });
    expect(html).toContain('14:00');
  });

  test('arrow → present for multi-day event (end_date ≠ start_date)', () => {
    const html = buildPopup({ ...BASE_TC, end_date: '2026-06-12' });
    expect(html).toContain('→');
  });

  test('no date arrow for single-day event (end_date = start_date)', () => {
    const html = buildPopup({ ...BASE_TC, end_date: '2026-06-10' });
    expect(html).not.toContain('2026-06-10 →');
  });
});

describe('buildPopup — source hanabi', () => {
  beforeEach(() => {
    vi.mocked(isFavorite).mockReturnValue(false);
  });

  test('contains Hanabi source badge', () => {
    expect(buildPopup(BASE_HANABI)).toContain('Hanabi');
  });

  test('XSS: title with HTML tags is escaped', () => {
    const html = buildPopup({ ...BASE_HANABI, title: '<b>bold</b>' });
    expect(html).not.toContain('<b>');
    expect(html).toContain('&lt;b&gt;');
  });

  test('fireworks_count badge rendered', () => {
    const html = buildPopup({
      ...BASE_HANABI,
      attributes: { fireworks_count: '10,000発' },
    });
    expect(html).toContain('10,000発');
  });

  test('expected_crowd badge rendered', () => {
    const html = buildPopup({
      ...BASE_HANABI,
      attributes: { expected_crowd: '50万人' },
    });
    expect(html).toContain('50万人');
  });

  test('food_stalls badge shown when value is あり', () => {
    const html = buildPopup({
      ...BASE_HANABI,
      attributes: { food_stalls: 'あり' },
    });
    expect(html).toContain('Food stalls');
  });

  test('food_stalls badge absent when value is not あり', () => {
    const html = buildPopup({
      ...BASE_HANABI,
      attributes: { food_stalls: 'なし' },
    });
    expect(html).not.toContain('Food stalls');
  });

  test('venue displayed when set', () => {
    const html = buildPopup({ ...BASE_HANABI, venue: '隅田川' });
    expect(html).toContain('隅田川');
  });

  test('access displayed when set', () => {
    const html = buildPopup({
      ...BASE_HANABI,
      attributes: { access: '浅草駅 3分' },
    });
    expect(html).toContain('浅草駅');
  });

  test('directions links present when lat/lng set', () => {
    const html = buildPopup({ ...BASE_HANABI, latitude: 35.71, longitude: 139.8 });
    expect(html).toContain('google.com/maps/dir');
    expect(html).toContain('maps.apple.com');
  });

  test('ICS calendar link points to /events/h-1.ics', () => {
    expect(buildPopup(BASE_HANABI)).toContain('/events/h-1.ics');
  });
});

const BASE_IJ = {
  id: 'ij-1',
  source: 'ij',
  title: 'Fukagawa Ryujin Reitaisai',
  start_date: '2026-05-01',
  end_date: null,
  url: 'https://ichiban-japan.com/festivals-tokyo-mai-2026/#fukagawa-ryujin-reitaisai',
  times: null,
  venue: 'temple Fukagawa Fudo-do',
  attributes: { neighbourhood: 'Monzen-Nakacho', official_link: 'https://x.example/' },
  price: null,
  latitude: null,
  longitude: null,
};

describe('buildPopup — source ij', () => {
  beforeEach(() => {
    vi.mocked(isFavorite).mockReturnValue(false);
  });

  test('contains Ichiban Japan source badge', () => {
    expect(buildPopup(BASE_IJ)).toContain('Ichiban Japan');
  });

  test('"Voir l\'événement" links to the official event page, not the Ichiban article', () => {
    const html = buildPopup(BASE_IJ);
    expect(html).toContain('href="https://x.example/"');           // official_link
    expect(html).not.toContain('href="https://ichiban-japan.com'); // pas l'article agrégateur
  });

  test('falls back to the Ichiban article URL when official_link is missing', () => {
    const html = buildPopup({ ...BASE_IJ, attributes: { neighbourhood: 'Asakusa' } });
    expect(html).toContain(`href="${BASE_IJ.url}"`);
  });

  test('venue and neighbourhood displayed', () => {
    const html = buildPopup(BASE_IJ);
    expect(html).toContain('temple Fukagawa Fudo-do');
    expect(html).toContain('Monzen-Nakacho');
  });

  test('XSS: title with <script> is escaped', () => {
    const html = buildPopup({ ...BASE_IJ, title: '<script>xss</script>' });
    expect(html).toContain('&lt;script&gt;');
    expect(html).not.toContain('<script>');
  });

  test('directions links absent when no lat/lng', () => {
    const html = buildPopup(BASE_IJ);
    expect(html).not.toContain('google.com/maps');
  });

  test('directions links present when lat/lng set', () => {
    const html = buildPopup({ ...BASE_IJ, latitude: 35.672, longitude: 139.798 });
    expect(html).toContain('google.com/maps/dir');
    expect(html).toContain('maps.apple.com');
  });

  test('multi-day arrow present when end_date differs', () => {
    const html = buildPopup({ ...BASE_IJ, end_date: '2026-05-05' });
    expect(html).toContain('→');
  });

  test('ICS calendar link points to /events/ij-1.ics', () => {
    expect(buildPopup(BASE_IJ)).toContain('/events/ij-1.ics');
  });
});
