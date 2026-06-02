export function fmtDate(d) { return d || '—'; }

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
