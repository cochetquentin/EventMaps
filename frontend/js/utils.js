export function fmtDate(d) { return d || '—'; }

export function haversineKm(lat1, lon1, lat2, lon2) {
  const R = 6371;
  const dLat = (lat2 - lat1) * Math.PI / 180;
  const dLon = (lon2 - lon1) * Math.PI / 180;
  const a = Math.sin(dLat / 2) ** 2
    + Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) * Math.sin(dLon / 2) ** 2;
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

export function fmtDistance(km) {
  return km < 1 ? `${Math.round(km * 1000)} m` : `${km.toFixed(1)} km`;
}

export function escapeHtml(str) {
  if (str == null) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

export function safeUrl(url) {
  if (!url || typeof url !== 'string') return '#';
  const u = url.trim();
  return (u.startsWith('http://') || u.startsWith('https://')) ? u : '#';
}

export function parseTimes(ev) {
  if (!ev.times) return ['', ''];
  const idx = ev.times.indexOf('-');
  return idx === -1 ? [ev.times, ''] : [ev.times.slice(0, idx), ev.times.slice(idx + 1)];
}

export function toSlash(d) { return d ? d.replace(/-/g, '/') : null; }

export function addDays(d, n) { return new Date(d.getTime() + n * 24 * 60 * 60 * 1000); }

export function isoDate(d) { return d.toISOString().slice(0, 10); }

export function todayJST() {
  const now = new Date();
  const jst = new Date(now.getTime() + 9 * 60 * 60 * 1000);
  jst.setUTCHours(0, 0, 0, 0);
  return jst;
}

export function computePresets() {
  const today = todayJST();
  const dow = today.getUTCDay();
  const daysFromMon = dow === 0 ? 6 : dow - 1;
  const mon = addDays(today, -daysFromMon);
  return {
    today:          [isoDate(today),          isoDate(today)],
    weekend:        [isoDate(addDays(mon,5)),  isoDate(addDays(mon,6))],
    'next-weekend': [isoDate(addDays(mon,12)), isoDate(addDays(mon,13))],
    week:           [isoDate(mon),             isoDate(addDays(mon,6))],
    'next-week':    [isoDate(addDays(mon,7)),  isoDate(addDays(mon,13))],
  };
}
