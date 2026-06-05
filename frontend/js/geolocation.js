/* global L */
import { map, proximityMode, setUserPosition, setProximityMode } from './state.js';
import { iconUser } from './config.js';
import { renderMarkers } from './markers.js';

let activeRequestId = 0;
let userMarker = null; // module-level pour être accessible par cancelGeolocation()

// Appelé par le Reset pour invalider toute requête GPS en cours et retirer le marker
export function cancelGeolocation() {
  activeRequestId++;
  if (userMarker) { map.removeLayer(userMarker); userMarker = null; }
}

export function setupGeolocation() {
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
        // Vérifier la fraîcheur AVANT de toucher le bouton — si Reset a invalidé la
        // requête entre-temps, la prochaine requête en cours doit garder son état ⏳
        if (myRequestId !== activeRequestId) return;
        btn.textContent = '📍';
        btn.disabled = false;
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
        if (myRequestId !== activeRequestId) return;
        btn.textContent = '📍';
        btn.disabled = false;
        alert("Impossible d'obtenir votre position : " + err.message);
      },
      { timeout: 10000, maximumAge: 60000 },
    );
  });
}
