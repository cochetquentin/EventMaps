// ── UI mobile : bottom-sheet glissable + en-tête repliable ──────────────────
// Actif uniquement sous 860px. Le desktop conserve son layout grille intact :
// aucun style inline n'est posé tant qu'on n'est pas en mode mobile, et on nettoie
// tout au repassage desktop.
import { map } from './state.js';

const MOBILE_MQ = '(max-width: 860px)';

// Points d'ancrage de la bottom-sheet, exprimés en hauteur VISIBLE depuis le bas.
// 'peek' ne laisse dépasser que la poignée + le compteur, pour dégager la carte.
const PEEK_VISIBLE = 76;              // px — poignée + #stats
const HALF_RATIO = 0.5;               // 50% de la hauteur de fenêtre
const SNAP = ['peek', 'half', 'full'];

let panel = null;
let currentSnap = 'peek';
let dragging = false;
let startY = 0;
let startTranslate = 0;
let panelHeight = 0;

const mq = window.matchMedia(MOBILE_MQ);

// translateY (px) correspondant à un point d'ancrage. 0 = panneau entièrement visible.
function translateForSnap(snap) {
  const h = panel.offsetHeight;
  if (snap === 'full') return 0;
  if (snap === 'half') return Math.max(0, h - window.innerHeight * HALF_RATIO);
  return Math.max(0, h - PEEK_VISIBLE); // peek
}

function applySnap(snap, animate = true) {
  currentSnap = snap;
  panel.style.transition = animate ? '' : 'none';
  panel.style.transform = `translateY(${translateForSnap(snap)}px)`;
}

// Choisit l'ancrage cible en fonction de la position finale et du sens du geste.
function nearestSnap(translate, direction) {
  const candidates = SNAP.map((s) => ({ s, t: translateForSnap(s) }));
  // Biais directionnel léger : un franc glissement pousse vers l'ancrage suivant.
  let best = candidates[0];
  let bestDist = Infinity;
  for (const c of candidates) {
    const dist = Math.abs(translate - c.t);
    if (dist < bestDist) { bestDist = dist; best = c; }
  }
  // direction > 0 = vers le bas (on réduit), < 0 = vers le haut (on agrandit)
  if (Math.abs(direction) > 24) {
    const idx = SNAP.indexOf(best.s);
    if (direction > 0 && idx > 0) return SNAP[idx - 1];
    if (direction < 0 && idx < SNAP.length - 1) return SNAP[idx + 1];
  }
  return best.s;
}

function onPointerDown(e) {
  if (!mq.matches) return;
  dragging = true;
  startY = e.clientY;
  panelHeight = panel.offsetHeight;
  const style = getComputedStyle(panel).transform;
  // Lit le translateY courant depuis la matrice calculée (m42).
  startTranslate = style && style !== 'none'
    ? new DOMMatrixReadOnly(style).m42
    : translateForSnap(currentSnap);
  panel.style.transition = 'none';
  panel.setPointerCapture?.(e.pointerId);
}

function onPointerMove(e) {
  if (!dragging) return;
  const delta = e.clientY - startY;
  const maxT = Math.max(0, panelHeight - PEEK_VISIBLE);
  const next = Math.min(maxT, Math.max(0, startTranslate + delta));
  panel.style.transform = `translateY(${next}px)`;
}

function onPointerUp(e) {
  if (!dragging) return;
  dragging = false;
  const delta = e.clientY - startY;
  const finalT = Math.min(
    Math.max(0, panelHeight - PEEK_VISIBLE),
    Math.max(0, startTranslate + delta),
  );
  applySnap(nearestSnap(finalT, delta));
}

// ── En-tête repliable (recherche / filtres) ─────────────────────────────────
function wireHeaderToggles() {
  const header = document.getElementById('app-header');
  const searchToggle = document.getElementById('search-toggle');
  const filtersToggle = document.getElementById('filters-toggle');

  searchToggle?.addEventListener('click', () => {
    const open = header.classList.toggle('search-open');
    searchToggle.setAttribute('aria-expanded', String(open));
    if (open) {
      header.classList.remove('filters-open');
      filtersToggle?.setAttribute('aria-expanded', 'false');
      document.getElementById('search-input')?.focus();
    }
  });

  filtersToggle?.addEventListener('click', () => {
    const open = header.classList.toggle('filters-open');
    filtersToggle.setAttribute('aria-expanded', String(open));
    if (open) {
      header.classList.remove('search-open');
      searchToggle?.setAttribute('aria-expanded', 'false');
    }
  });
}

// ── Bascule mobile / desktop ────────────────────────────────────────────────
function syncMode() {
  if (mq.matches) {
    applySnap('peek', false);
  } else {
    // Repasse en desktop : on efface les styles inline pour rendre la main au CSS grille.
    panel.style.transform = '';
    panel.style.transition = '';
  }
  // Leaflet doit recalculer sa taille après tout changement de layout.
  map?.invalidateSize();
}

export function initMobileUI() {
  panel = document.getElementById('list-panel');
  if (!panel) return;

  const handle = panel.querySelector('.sheet-handle');
  const stats = document.getElementById('stats');
  // La préhension se fait sur la poignée + le compteur ; #event-list garde son scroll natif.
  [handle, stats].forEach((el) => el?.addEventListener('pointerdown', onPointerDown));
  window.addEventListener('pointermove', onPointerMove);
  window.addEventListener('pointerup', onPointerUp);
  window.addEventListener('pointercancel', onPointerUp);

  wireHeaderToggles();

  mq.addEventListener('change', syncMode);
  window.addEventListener('orientationchange', () => setTimeout(syncMode, 150));
  syncMode();
}
