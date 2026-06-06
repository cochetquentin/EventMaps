import { allEvents, markerMap } from './state.js';

function fold(str) {
  const out = [];
  while (str.length > 75) {
    out.push(str.slice(0, 75));
    str = ' ' + str.slice(75);
  }
  out.push(str);
  return out.join('\r\n');
}

function escapeICS(str) {
  return (str || '').replace(/\\/g, '\\\\').replace(/;/g, '\\;').replace(/,/g, '\\,').replace(/\n/g, '\\n');
}

function addDay(iso) {
  const d = new Date(iso + 'T00:00:00Z');
  d.setUTCDate(d.getUTCDate() + 1);
  return d.toISOString().slice(0, 10).replace(/-/g, '');
}

export function downloadICS() {
  // markerMap reflects exactly the events currently visible after all filters
  // (pills, categories, favorites, dates) — same as what renderMarkers produces.
  const visible = allEvents.filter(ev => markerMap.has(ev.id));

  const lines = [
    'BEGIN:VCALENDAR',
    'VERSION:2.0',
    'PRODID:-//EventMaps//Tokyo Events//EN',
    'CALSCALE:GREGORIAN',
  ];

  for (const ev of visible) {
    lines.push('BEGIN:VEVENT');
    lines.push(fold(`SUMMARY:${escapeICS(ev.title)}`));
    lines.push(`UID:${ev.id}@eventmaps`);
    if (ev.start_date) {
      lines.push(`DTSTART;VALUE=DATE:${ev.start_date.replace(/-/g, '')}`);
      const end = ev.end_date || ev.start_date;
      lines.push(`DTEND;VALUE=DATE:${addDay(end)}`);
    }
    lines.push(fold(`URL:${ev.url}`));
    const location = ev.venue || ev.attributes?.location_name || null;
    if (location) lines.push(fold(`LOCATION:${escapeICS(location)}`));
    if (ev.price) lines.push(fold(`DESCRIPTION:${escapeICS(ev.price)}`));
    lines.push('END:VEVENT');
  }

  lines.push('END:VCALENDAR');

  const blob = new Blob([lines.join('\r\n')], { type: 'text/calendar;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'events.ics';
  a.click();
  URL.revokeObjectURL(url);
}
