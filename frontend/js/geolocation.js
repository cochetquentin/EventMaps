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
    // Contexte non sécurisé (page servie en HTTP hors localhost) : les navigateurs,
    // en particulier sur mobile, bloquent getCurrentPosition avant même de demander
    // la permission. On l'explique clairement plutôt que d'afficher le message natif.
    if (!window.isSecureContext) {
      alert(
        "La géolocalisation nécessite une connexion sécurisée (HTTPS). "
        + "L'application est ouverte en HTTP, ce que les navigateurs mobiles bloquent. "
        + "Ouvre-la via une URL https:// pour te localiser.",
      );
      return;
    }
    activeRequestId++;
    const myRequestId = activeRequestId;
    btn.classList.add('loading');
    btn.disabled = true;
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        // Vérifier la fraîcheur AVANT de toucher le bouton — si Reset a invalidé la
        // requête entre-temps, la prochaine requête en cours doit garder son état ⏳
        if (myRequestId !== activeRequestId) return;
        btn.classList.remove('loading');
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
        btn.classList.remove('loading');
        btn.disabled = false;
        const messages = {
          1: "Localisation refusée. Autorise l'accès à ta position dans les réglages du navigateur.",
          2: 'Position indisponible pour le moment. Réessaie dans un instant.',
          3: 'La localisation a pris trop de temps. Réessaie.',
        };
        alert("Impossible d'obtenir votre position : "
          + (messages[err.code] || err.message));
      },
      { timeout: 10000, maximumAge: 60000 },
    );
  });
}
