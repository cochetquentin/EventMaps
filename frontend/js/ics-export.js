import { allEvents, markerMap } from './state.js';

const _encoder = new TextEncoder();

// Fold an ICS content line to max 75 UTF-8 octets per line (RFC 5545 §3.1).
// Continuation lines start with a single SPACE.
function fold(str) {
  const out = [];
  let line = '';
  let lineBytes = 0;
  for (const char of str) {
    const charBytes = _encoder.encode(char).length;
    if (lineBytes + charBytes > 75) {
      out.push(line);
      line = ' ' + char;
      lineBytes = 1 + charBytes; // leading space = 1 byte
    } else {
      line += char;
      lineBytes += charBytes;
    }
  }
  out.push(line);
  return out.join('\r\n');
}

function escapeICS(str) {
  return (str || '').replace(/\\/g, '\\\\').replace(/;/g, '\\;').replace(/,/g, '\\,').replace(/\n/g, '\\n');
}

// Format a Date object as ICS UTC datetime: YYYYMMDDTHHMMSSZ
function toUtcStamp(d) {
  return d.toISOString().replace(/[-:]/g, '').slice(0, 15) + 'Z';
}

// Convert an ISO date + "HH:MM" JST string to a UTC Date.
// Tokyo = UTC+9, no DST — handles midnight wraparound automatically.
function jstToUtcDate(dateIso, hm) {
  return new Date(`${dateIso}T${hm}:00+09:00`);
}

export function downloadICS() {
  // markerMap reflects exactly the events currently visible after all filters
  // (pills, categories, favorites, dates) — same as what renderMarkers produces.
  const visible = allEvents.filter(ev => markerMap.has(ev.id));
  if (visible.length === 0) return; // nothing to export
  const stamp = toUtcStamp(new Date());

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
    lines.push(`DTSTAMP:${stamp}`);
    if (ev.start_date) {
      const endDate = ev.end_date || ev.start_date;
      // Parse times field: "HH:MM-HH:MM" or "HH:MM"
      const parts = ev.times ? ev.times.split('-').map(s => s.trim()) : null;
      const startHM = parts ? parts[0] : null;
      const endHM = parts && parts.length > 1 ? parts[1] : null;
      if (startHM) {
        // Emit UTC datetimes — no VTIMEZONE component needed, handles midnight wraparound
        const startUtc = jstToUtcDate(ev.start_date, startHM);
        lines.push(`DTSTART:${toUtcStamp(startUtc)}`);
        const endUtc = endHM
          ? jstToUtcDate(endDate, endHM)
          : new Date(startUtc.getTime() + 60 * 60 * 1000); // +1 hour
        lines.push(`DTEND:${toUtcStamp(endUtc)}`);
      } else {
        // Date-only event
        lines.push(`DTSTART;VALUE=DATE:${ev.start_date.replace(/-/g, '')}`);
        const d = new Date(endDate + 'T00:00:00Z');
        d.setUTCDate(d.getUTCDate() + 1);
        lines.push(`DTEND;VALUE=DATE:${d.toISOString().slice(0, 10).replace(/-/g, '')}`);
      }
    }
    lines.push(fold(`URL:${ev.url}`));
    const location = ev.venue || ev.attributes?.location_name || null;
    if (location) lines.push(fold(`LOCATION:${escapeICS(location)}`));
    if (ev.price) lines.push(fold(`DESCRIPTION:${escapeICS(ev.price)}`));
    lines.push('END:VEVENT');
  }

  lines.push('END:VCALENDAR');

  // RFC 5545: every content line ends with CRLF, including the last one.
  const blob = new Blob([lines.join('\r\n') + '\r\n'], { type: 'text/calendar;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'events.ics';
  a.click();
  // Delay revocation to ensure the browser has consumed the URL before it is released.
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
