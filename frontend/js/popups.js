import { fmtDate, parseTimes } from './utils.js';
import { isFavorite } from './favorites.js';

export function buildPopup(ev) {
  const attrs = ev.attributes || {};
  if (ev.source === 'tc') {
    const [st, et] = parseTimes(ev);
    const date  = ev.end_date && ev.end_date !== ev.start_date
      ? `📅 ${fmtDate(ev.start_date)} → ${fmtDate(ev.end_date)}`
      : `📅 ${fmtDate(ev.start_date)}`;
    const time  = st ? `🕐 ${st}${et ? ' – ' + et : ''}` : '';
    const loc   = attrs.location_name ? `📍 ${attrs.location_name}` : '';
    const meta  = [date, time, loc].filter(Boolean).join('<br>');
    const badge = ev.price ? `<div class="pop-badges"><span class="pop-badge">${ev.price}</span></div>` : '';
    return `<div class="pop"><div class="pop-bar tc"></div><div class="pop-body">
      <div class="pop-source tc">Tokyo Cheapo</div>
      <div class="pop-title">${ev.title}</div>
      <div class="pop-meta">${meta}</div>${badge}
      <div class="pop-actions" style="flex-direction:column;gap:6px;">
        <div style="display:flex;gap:6px;">
          <a class="pop-btn primary" href="${ev.url}" target="_blank" style="flex:1">Voir l'événement →</a>
          <button class="fav-btn pop-fav-btn ${isFavorite(ev.id) ? 'active' : ''}" data-fav-id="${ev.id}" title="Favoris">${isFavorite(ev.id) ? '★' : '☆'}</button>
        </div>
        <div style="display:flex;gap:6px;">
          <a class="pop-btn secondary" href="https://www.google.com/maps/dir/?api=1&destination=${ev.latitude},${ev.longitude}" target="_blank">🗺 Google</a>
          <a class="pop-btn secondary" href="https://maps.apple.com/?daddr=${ev.latitude},${ev.longitude}" target="_blank"> Apple</a>
        </div>
        <a href="/events/${ev.id}.ics" style="font-size:11px;text-align:center;color:var(--muted);text-decoration:underline;">📅 Ajouter au calendrier</a>
      </div></div></div>`;
  } else {
    const [st, et] = parseTimes(ev);
    const date   = `📅 ${fmtDate(ev.start_date)}`;
    const time   = st ? `🕐 ${st}${et ? ' – ' + et : ''}` : '';
    const venue  = ev.venue     ? `📍 ${ev.venue}`     : '';
    const access = attrs.access ? `🚉 ${attrs.access}` : '';
    const meta   = [date, time, venue, access].filter(Boolean).join('<br>');
    const bs = [
      attrs.fireworks_count ? `🎇 ${attrs.fireworks_count}` : null,
      attrs.expected_crowd  ? `👥 ${attrs.expected_crowd}`  : null,
      attrs.food_stalls  === 'あり' ? '🍢 Food stalls'  : null,
      attrs.paid_seating === 'あり' ? '🎫 Paid seating' : null,
    ].filter(Boolean);
    const badges = bs.length
      ? `<div class="pop-badges">${bs.map(b => `<span class="pop-badge">${b}</span>`).join('')}</div>`
      : '';
    return `<div class="pop"><div class="pop-bar hanabi"></div><div class="pop-body">
      <div class="pop-source hanabi">🎆 Hanabi</div>
      <div class="pop-title">${ev.title}</div>
      <div class="pop-meta">${meta}</div>${badges}
      <div class="pop-actions" style="flex-direction:column;gap:6px;">
        <div style="display:flex;gap:6px;">
          <a class="pop-btn primary" href="${ev.url}" target="_blank" style="flex:1">Voir l'événement →</a>
          <button class="fav-btn pop-fav-btn ${isFavorite(ev.id) ? 'active' : ''}" data-fav-id="${ev.id}" title="Favoris">${isFavorite(ev.id) ? '★' : '☆'}</button>
        </div>
        <div style="display:flex;gap:6px;">
          <a class="pop-btn secondary" href="https://www.google.com/maps/dir/?api=1&destination=${ev.latitude},${ev.longitude}" target="_blank">🗺 Google</a>
          <a class="pop-btn secondary" href="https://maps.apple.com/?daddr=${ev.latitude},${ev.longitude}" target="_blank"> Apple</a>
        </div>
        <a href="/events/${ev.id}.ics" style="font-size:11px;text-align:center;color:var(--muted);text-decoration:underline;">📅 Ajouter au calendrier</a>
      </div></div></div>`;
  }
}
