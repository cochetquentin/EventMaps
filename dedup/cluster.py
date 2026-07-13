"""Regroupement d'un lot d'événements en clusters de doublons.

Union-find sur les paires jugées doublons par :func:`dedup.matching.classify_pair`,
puis choix d'un représentant déterministe par cluster (le ``canonical_id``).
"""

from __future__ import annotations

from dedup.matching import is_duplicate, same_source_same_event
from dedup.normalize import event_coords, event_venue
from models.event import Event


class _UnionFind:
    def __init__(self, ids: list[str]) -> None:
        self._parent = {i: i for i in ids}

    def find(self, x: str) -> str:
        root = x
        while self._parent[root] != root:
            root = self._parent[root]
        # Compression de chemin.
        while self._parent[x] != root:
            self._parent[x], x = root, self._parent[x]
        return root

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self._parent[ra] = rb


def _representative_key(event: Event) -> tuple:
    """Clé de tri : on préfère un événement AVEC coordonnées (garde le pin sur la
    carte), puis AVEC nom de lieu, puis l'``id`` le plus petit pour un choix
    totalement déterministe et stable entre exécutions."""
    return (
        0 if event_coords(event) is not None else 1,
        0 if event_venue(event) else 1,
        event.id,
    )


def canonical_representative(events: list[Event]) -> Event:
    """Élire l'événement représentant d'un cluster (le plus complet, déterministe)."""
    return min(events, key=_representative_key)


def assign_canonical_ids(events: list[Event]) -> dict[str, str]:
    """Associer à chaque ``event.id`` le ``canonical_id`` de son cluster.

    Un événement seul (aucun doublon) est son propre représentant. Les doublons
    exacts (même ``id``, ex. existant + re-scrape) sont fusionnés en amont : on
    ne compare qu'une fois chaque ``id`` unique.

    Complexité : O(n²) comparaisons, mais :func:`classify_pair` court-circuite
    dès que les dates ne se chevauchent pas, donc la partie coûteuse (fuzzy) ne
    s'exécute que sur des paires temporellement plausibles.
    """
    # Déduplique par id en gardant la première occurrence rencontrée.
    unique: dict[str, Event] = {}
    for event in events:
        unique.setdefault(event.id, event)

    items = list(unique.values())
    uf = _UnionFind([e.id for e in items])

    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            a, b = items[i], items[j]
            # Deux régimes disjoints : au sein d'une même source, l'identité par
            # (URL + nom de lieu) fait foi (dates ignorées, géo non consultée) ;
            # entre sources différentes, on applique la similarité floue stricte.
            merge = same_source_same_event(a, b) if a.source == b.source else is_duplicate(a, b)
            if merge:
                uf.union(a.id, b.id)

    # Regroupe par racine, puis élit le représentant de chaque cluster.
    clusters: dict[str, list[Event]] = {}
    for event in items:
        clusters.setdefault(uf.find(event.id), []).append(event)

    mapping: dict[str, str] = {}
    for members in clusters.values():
        canonical = canonical_representative(members).id
        for member in members:
            mapping[member.id] = canonical
    return mapping
