"""Déduplication d'événements cross-source.

Couche PURE (aucune I/O, aucune dépendance DB) : elle décide si deux
événements sont des doublons et regroupe un lot en clusters. La persistance
(colonne ``canonical_id``) est faite par la couche DB, jamais ici.

Principe directeur : **zéro faux positif**. Un doublon n'est déclaré que si
plusieurs signaux indépendants concordent (dates compatibles ET titre très
proche ET lieu confirmé). Toute donnée manquante fait échouer une porte et
l'événement reste distinct — on préfère un doublon manqué à une fusion à tort.
"""

from dedup.cluster import assign_canonical_ids, canonical_representative
from dedup.matching import PairVerdict, classify_pair, is_duplicate

__all__ = [
    "PairVerdict",
    "assign_canonical_ids",
    "canonical_representative",
    "classify_pair",
    "is_duplicate",
]
