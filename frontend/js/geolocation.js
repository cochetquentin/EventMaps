/* global L */
import { map } from './state.js';
import { iconUser } from './config.js';

export function setupGeolocation() {
  let userMarker = null;

  document.getElementById('locate-btn').addEventListener('click', () => {
    if (!navigator.geolocation) {
      alert("La géolocalisation n'est pas supportée par ce navigateur.");
      return;
    }
    const btn = document.getElementById('locate-btn');
    btn.textContent = '⏳';
    btn.disabled = true;
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        btn.textContent = '📍';
        btn.disabled = false;
        const lat = pos.coords.latitude, lng = pos.coords.longitude;
        if (userMarker) map.removeLayer(userMarker);
        userMarker = L.marker([lat, lng], { icon: iconUser })
          .bindPopup('📍 Vous êtes ici').addTo(map);
        map.setView([lat, lng], 13, { animate: true });
      },
      (err) => {
        btn.textContent = '📍';
        btn.disabled = false;
        alert("Impossible d'obtenir votre position : " + err.message);
      },
      { timeout: 10000, maximumAge: 60000 },
    );
  });
}
