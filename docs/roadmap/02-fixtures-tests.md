# Fixtures et stratégie de test des scrapers

[Retour à l'index](README.md)

## Diagnostic

Les tests unitaires sont nombreux et la couverture est élevée, mais la robustesse d'un scraper dépend surtout de la représentativité des HTML utilisés.

| Source | Fixtures actuelles | Diagnostic |
|---|---:|---|
| Tokyo Cheapo | 1 listing + 3 pages événement | Fichiers de 877 à 1 237 octets, HTML lisible et minimal : fixtures reconstruites, insuffisantes pour refléter le DOM réel |
| Hanabi Walker | 1 listing + 2 fragments événement | Fichiers de 477 à 1 345 octets ; la page de données et la carte semblent être deux fragments d'un même événement : couverture réelle insuffisante |
| Time Out Tokyo | 1 listing + 3 pages événement | Trois captures volumineuses (environ 136–380 Ko) semblent provenir de pages réelles ; une fixture de fallback de 470 octets est synthétique ; provenance non documentée |

Les fixtures synthétiques gardent une valeur pour tester un cas minimal précis. Elles ne doivent pas être présentées comme tests de contrat représentatifs. Les pages réelles doivent être figées, nettoyées uniquement pour les secrets/données inutiles, et ne jamais être récupérées en direct pendant la CI.

## TEST-001 — Définir la politique de fixtures

- **Statut : Terminé**
- **Priorité : P0**
- **Suivi :** https://github.com/cochetquentin/EventMaps/issues/50

**Actions.** Documenter deux catégories : `real` pour captures réelles de contrat et `synthetic` pour cas unitaires minimaux ; définir les règles de provenance, date de capture, URL source, anonymisation, taille et mise à jour.

**Critères d'acceptation.** Chaque fixture possède une catégorie et une provenance lisible sans exécuter le test ; les tests réseau live restent interdits en CI.

## TEST-002 — Réorganiser et inventorier les fixtures par source

- **Statut : Terminé**
- **Priorité : P1**
- **Dépendances :** TEST-001
- **Suivi :** https://github.com/cochetquentin/EventMaps/pull/83

**Actions.** Créer une arborescence par source et catégorie, adopter des noms décrivant le cas, et ajouter un manifeste léger contenant URL, date de capture, structure couverte et éventuelles transformations.

**Critères d'acceptation.** Un développeur peut savoir pourquoi chaque fichier existe et quels tests le consomment ; aucune fixture orpheline.

## TEST-003 — Constituer un corpus réel Tokyo Cheapo

- **Statut : À faire**
- **Priorité : P1**
- **Dépendances :** TEST-001, TEST-002
- **Suivi :** https://github.com/cochetquentin/EventMaps/issues/58

**Corpus cible.** Environ cinq pages événement réelles et au moins deux listings : événement complet, sans description, dates floues ou multi-jour, plusieurs lieux, données optionnelles absentes, et variations de listing observées.

**Critères d'acceptation.** Les parseurs principaux sont exercés sur des captures réelles ; les petites fixtures synthétiques restantes sont explicitement étiquetées.

## TEST-004 — Constituer un corpus réel Hanabi Walker

- **Statut : À faire**
- **Priorité : P1**
- **Dépendances :** TEST-001, TEST-002
- **Suivi :** https://github.com/cochetquentin/EventMaps/issues/59

**Corpus cible.** Environ cinq événements réels issus de régions et structures différentes, avec leurs pages/fragments nécessaires : date valide, date reportée/annulée, coordonnées présentes/absentes, champs de tableau variables, et listings représentatifs.

**Critères d'acceptation.** Les variantes réellement observées sont couvertes ; les fragments appartenant au même événement sont liés dans le manifeste.

## TEST-005 — Qualifier et compléter le corpus Time Out Tokyo

- **Statut : Terminé**
- **Priorité : P1**
- **Dépendances :** TEST-001, TEST-002
- **Suivi :** https://github.com/cochetquentin/EventMaps/pull/84

**Actions.** Confirmer la provenance des captures existantes, ajouter les métadonnées manquantes et compléter jusqu'à environ cinq pages représentatives : événement JSON-LD, article, données incomplètes, coordonnées absentes et variation de listing.

**Critères d'acceptation.** Les captures réelles existantes ne sont pas remplacées inutilement ; les trous de couverture sont explicitement fermés.

## TEST-006 — Ajouter des assertions de contrat et de qualité d'extraction

- **Statut : Terminé**
- **Priorité : P1**
- **Dépendances :** TEST-003, TEST-004, TEST-005
- **Suivi :** https://github.com/cochetquentin/EventMaps/issues/61

**Actions.** Pour chaque capture réelle, vérifier les champs essentiels et les erreurs attendues ; tester les taux d'extraction d'un listing et l'absence de perte silencieuse ; conserver séparément les tests unitaires de fonctions de parsing.

**Critères d'acceptation.** Une modification cassant un sélecteur réel échoue avec un message identifiant la source et la fixture ; les champs essentiels ne peuvent pas tous devenir vides sans échec.

## TEST-007 — Définir le renouvellement contrôlé des captures

- **Statut : Terminé**
- **Priorité : P2**
- **Dépendances :** TEST-001
- **Suivi :** https://github.com/cochetquentin/EventMaps/pull/89

**Actions.** Fournir une procédure manuelle ou un script opt-in respectueux des sites, avec user-agent, délais, revue du diff et vérification des droits ; ne pas automatiser la collecte en CI.

**Critères d'acceptation.** Une capture peut être renouvelée de façon reproductible et revue avant commit ; aucun test n'appelle un site tiers.
