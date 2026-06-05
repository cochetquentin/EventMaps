/* global L */
import { map, proximityMode, setUserPosition, setProximityMode } from './state.js';
import { iconUser } from './config.js';
import { renderMarkers } from './markers.js';

let activeRequestId = 0;

// Appelé par le Reset pour invalider toute requête GPS en cours
export function cancelGeolocation() {
  activeRequestId++;
}

export function setupGeolocation() {
  let userMarker = null;

  document.getElementById('locate-btn').addEventListener('click', () => {
    const btn = document.getElementById('locate-btn');

    // Toggle off si déjà en mode proximité
    if (proximityMode) {
      activeRequestId++;
      setProximityMode(false);
      setUserPosition(null);
      btn.classList.remove('active');
      if (userMarker) { map.removeLayer(userMarker); userMarker = null; }
      renderMarkers();
      return;
    }

    if (!navigator.geolocation) {
      alert("La géolocalisation n'est pas supportée par ce navigateur.");
      return;
    }
    activeRequestId++;
    const myRequestId = activeRequestId;
    btn.textContent = '⏳';
    btn.disabled = true;
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        btn.textContent = '📍';
        btn.disabled = false;
        // Callback obsolète si Reset a été cliqué pendant la requête
        if (myRequestId !== activeRequestId) return;
        const lat = pos.coords.latitude, lng = pos.coords.longitude;
        setUserPosition({ lat, lng });
        setProximityMode(true);
        btn.classList.add('active');
        if (userMarker) map.removeLayer(userMarker);
        userMarker = L.marker([lat, lng], { icon: iconUser })
          .bindPopup('📍 Vous êtes ici').addTo(map);
        map.setView([lat, lng], 13, { animate: true });
        renderMarkers();
      },
      (err) => {
        btn.textContent = '📍';
        btn.disabled = false;
        if (myRequestId !== activeRequestId) return;
        alert("Impossible d'obtenir votre position : " + err.message);
      },
      { timeout: 10000, maximumAge: 60000 },
    );
  });
}
