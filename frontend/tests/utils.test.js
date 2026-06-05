import { describe, test, expect, beforeEach, afterEach, vi } from 'vitest';
import { escapeHtml, safeUrl, parseTimes, computePresets } from '../js/utils.js';

describe('escapeHtml', () => {
  test('null returns empty string', () => expect(escapeHtml(null)).toBe(''));
  test('undefined returns empty string', () => expect(escapeHtml(undefined)).toBe(''));
  test('0 (falsy non-null) is converted to string "0"', () => expect(escapeHtml(0)).toBe('0'));
  test('ampersand escaped', () => expect(escapeHtml('a&b')).toBe('a&amp;b'));
  test('less-than escaped', () => expect(escapeHtml('<b>')).toBe('&lt;b&gt;'));
  test('greater-than escaped', () => expect(escapeHtml('a>b')).toBe('a&gt;b'));
  test('double quote escaped', () => expect(escapeHtml('"hi"')).toBe('&quot;hi&quot;'));
  test("single quote escaped", () => expect(escapeHtml("it's")).toBe('it&#39;s'));
  test('full XSS payload fully escaped', () => {
    expect(escapeHtml('<script>alert("xss")</script>')).toBe(
      '&lt;script&gt;alert(&quot;xss&quot;)&lt;/script&gt;'
    );
  });
  test('safe string unchanged', () => expect(escapeHtml('hello world')).toBe('hello world'));
});

describe('safeUrl', () => {
  test.each([null, undefined, ''])('nullish/empty "%s" returns "#"', (url) =>
    expect(safeUrl(url)).toBe('#')
  );
  test('javascript: URL returns "#"', () => expect(safeUrl('javascript:alert(1)')).toBe('#'));
  test('ftp:// URL returns "#"', () => expect(safeUrl('ftp://x.com')).toBe('#'));
  test('relative path returns "#"', () => expect(safeUrl('/relative')).toBe('#'));
  test('http:// URL accepted', () => expect(safeUrl('http://example.com')).toBe('http://example.com'));
  test('https:// URL accepted', () => expect(safeUrl('https://example.com')).toBe('https://example.com'));
  test('URL with surrounding spaces is trimmed', () =>
    expect(safeUrl('  https://x.com  ')).toBe('https://x.com')
  );
});

describe('parseTimes', () => {
  test('no times field returns ["", ""]', () => expect(parseTimes({})).toEqual(['', '']));
  test('times=null returns ["", ""]', () => expect(parseTimes({ times: null })).toEqual(['', '']));
  test('times=undefined returns ["", ""]', () => expect(parseTimes({ times: undefined })).toEqual(['', '']));
  test('time range split on first dash', () =>
    expect(parseTimes({ times: '14:00-16:00' })).toEqual(['14:00', '16:00'])
  );
  test('single time (no dash) returns [time, ""]', () =>
    expect(parseTimes({ times: '14:00' })).toEqual(['14:00', ''])
  );
  test('spaced separator preserves spaces in slices', () =>
    expect(parseTimes({ times: '14:00 - 16:00' })).toEqual(['14:00 ', ' 16:00'])
  );
});

describe('computePresets', () => {
  // Fixture: fix time to mercredi 2026-06-03 JST
  // 2026-06-02 21:00 UTC + 9h = 2026-06-03 06:00 UTC → JST midnight = 2026-06-03 00:00 UTC
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-06-02T21:00:00.000Z'));
  });
  afterEach(() => vi.useRealTimers());

  test('today preset is current JST date', () => {
    const p = computePresets();
    expect(p.today).toEqual(['2026-06-03', '2026-06-03']);
  });
  test('week starts on Monday of current week', () => {
    const p = computePresets();
    expect(p.week[0]).toBe('2026-06-01');
  });
  test('week ends on Sunday of current week', () => {
    const p = computePresets();
    expect(p.week[1]).toBe('2026-06-07');
  });
  test('weekend is Saturday–Sunday of current week', () => {
    const p = computePresets();
    expect(p.weekend).toEqual(['2026-06-06', '2026-06-07']);
  });
  test('next-week starts Monday after current week', () => {
    const p = computePresets();
    expect(p['next-week'][0]).toBe('2026-06-08');
  });
  test('next-weekend is Saturday–Sunday of next week', () => {
    const p = computePresets();
    expect(p['next-weekend']).toEqual(['2026-06-13', '2026-06-14']);
  });

  test('Sunday: week starts on previous Monday', () => {
    // 2026-06-06 21:00 UTC + 9h = 2026-06-07 06:00 UTC → dimanche JST
    vi.setSystemTime(new Date('2026-06-06T21:00:00.000Z'));
    const p = computePresets();
    expect(p.week[0]).toBe('2026-06-01');
    expect(p.today).toEqual(['2026-06-07', '2026-06-07']);
  });

  test('Monday: daysFromMon=0, week starts on same day', () => {
    // 2026-06-07 21:00 UTC + 9h = 2026-06-08 06:00 UTC → lundi JST
    vi.setSystemTime(new Date('2026-06-07T21:00:00.000Z'));
    const p = computePresets();
    expect(p.today).toEqual(['2026-06-08', '2026-06-08']);
    expect(p.week[0]).toBe('2026-06-08');
  });
});
