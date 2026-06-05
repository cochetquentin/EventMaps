import { setSelectedEventId } from './state.js';
import { fmtDate } from './utils.js';

const SAFE_PROTOCOLS = /^https?:\/\//i;
function safeUrl(url) { return (url && SAFE_PROTOCOLS.test(url)) ? url : null; }

function _appendMetaLine(container, emoji, text) {
  const row = document.createElement('div');
  row.className = 'drawer-meta-line';
  const e = document.createElement('span'); e.textContent = emoji;
  const t = document.createElement('span'); t.textContent = text;
  row.append(e, t);
  container.appendChild(row);
}

function _escHandler(e) { if (e.key === 'Escape') closeDrawer(); }

export function openDrawer(ev) {
  const panel = document.getElementById('event-drawer');
  if (!panel) return;
  setSelectedEventId(ev.id);
  const attrs = ev.attributes || {};

  // Source bar + labels
  panel.querySelector('.drawer-source-bar').className =
    `drawer-source-bar ${ev.source}`;
  panel.querySelector('.drawer-source-label').textContent =
    ev.source === 'tc' ? 'Tokyo Cheapo' : '🎆 Hanabi';
  panel.querySelector('.drawer-title').textContent = ev.title || '';

  // Meta lines — textContent uniquement (pas d'innerHTML avec données utilisateur)
  const metaEl = panel.querySelector('.drawer-meta');
  metaEl.innerHTML = '';
  _appendMetaLine(metaEl, '📅', fmtDate(ev.start_date || ev.date));
  if (ev.times) _appendMetaLine(metaEl, '🕐', ev.times);
  const place = ev.source === 'tc' ? attrs.location_name : ev.venue;
  if (place) _appendMetaLine(metaEl, '📍', place);
  if (attrs.access) _appendMetaLine(metaEl, '🚉', attrs.access);

  // Description longue — textContent (jamais innerHTML avec données scrapées)
  const descSection = panel.querySelector('.drawer-description');
  const descText = attrs.description || ev.description;
  if (descText) {
    descSection.style.display = '';
    descSection.querySelector('.drawer-section-content').textContent = descText;
  } else {
    descSection.style.display = 'none';
  }

  // Attributs spéciaux (parking, rain_policy, etc.)
  const attrEl = panel.querySelector('.drawer-attributes');
  attrEl.innerHTML = '';
  const extraAttrs = [
    ['🅿️', 'Parking', attrs.parking],
    ['🌧', 'En cas de pluie', attrs.rain_policy],
    ['💺', 'Places assises payantes', attrs.paid_seating],
    ['🍜', 'Stands alimentaires', attrs.food_stalls],
  ];
  extraAttrs.forEach(([emoji, label, val]) => {
    if (!val) return;
    const sec = document.createElement('div');
    sec.className = 'drawer-section';
    const title = document.createElement('div');
    title.className = 'drawer-section-title';
    title.textContent = label;
    const content = document.createElement('div');
    content.className = 'drawer-section-content';
    content.textContent = `${emoji} ${val}`;
    sec.append(title, content);
    attrEl.appendChild(sec);
  });

  // Liens actions — chaque candidat validé indépendamment pour permettre le fallback
  // TC stocke attrs.official_link, Hanabi stocke attrs.official_site
  const eventUrl = safeUrl(attrs.official_link) || safeUrl(attrs.official_site) || safeUrl(ev.url);
  const linkEvent = panel.querySelector('.drawer-link-event');
  linkEvent.href = eventUrl || '#';
  linkEvent.style.display = eventUrl ? '' : 'none';

  if (ev.latitude && ev.longitude) {
    const coords = `${ev.latitude},${ev.longitude}`;
    panel.querySelector('.drawer-link-google').href =
      `https://www.google.com/maps/dir/?api=1&destination=${coords}`;
    panel.querySelector('.drawer-link-apple').href =
      `https://maps.apple.com/?daddr=${coords}`;
    panel.querySelector('.drawer-link-google').style.display = '';
    panel.querySelector('.drawer-link-apple').style.display = '';
  } else {
    panel.querySelector('.drawer-link-google').style.display = 'none';
    panel.querySelector('.drawer-link-apple').style.display = 'none';
  }
  panel.querySelector('.drawer-link-ical').href =
    `/events/${encodeURIComponent(ev.id)}.ics`;

  panel.classList.add('open');
  document.addEventListener('keydown', _escHandler);
}

export function closeDrawer() {
  const panel = document.getElementById('event-drawer');
  if (panel) panel.classList.remove('open');
  document.removeEventListener('keydown', _escHandler);
}

export function initDrawer() {
  const panel = document.getElementById('event-drawer');
  if (!panel) return;
  panel.querySelector('.drawer-backdrop').addEventListener('click', closeDrawer);
  panel.querySelector('#drawer-close').addEventListener('click', closeDrawer);
}
