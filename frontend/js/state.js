// Shared mutable state — use setters to reassign primitives (live bindings)
export let allEvents = [];
export let showOnlyFavorites = false;
export let map = null;
export let clusterGroup = null;
export const markerMap = new Map();
export const deactivatedPills = new Set();
export let userPosition = null;   // { lat, lng } | null
export let proximityMode = false;

export function setAllEvents(v) { allEvents = v; }
export function setShowOnlyFavorites(v) { showOnlyFavorites = v; }
export function setMap(v) { map = v; }
export function setClusterGroup(v) { clusterGroup = v; }
export function setUserPosition(v) { userPosition = v; }
export function setProximityMode(v) { proximityMode = v; }
