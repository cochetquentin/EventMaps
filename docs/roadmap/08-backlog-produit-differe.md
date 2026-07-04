# Archive du backlog produit différé

[Retour à l'index](README.md)

## Rôle de ce document

Ce document conserve les propositions produit non terminées de l'ancien `REPO_ROADMAP_AUDIT.md` sans les intégrer à la phase de stabilisation. Elles sont **différées** : elles ne doivent pas être planifiées avant la revue de sortie STAB-004, puis devront être réévaluées contre le produit et le code du moment.

Ces entrées ne sont pas des tâches de stabilisation et n'utilisent donc pas les statuts **À faire / En cours / Terminé**. Leur présence évite de perdre les décisions historiques lors de la suppression de l'ancien audit.

## BACKLOG-FEAT-001 — Recherche et filtres serveur complets

- **Décision : Différé après stabilisation ; périmètre à réévaluer**
- **Origine :** FEAT-001
- **Implémenté :** https://github.com/cochetquentin/EventMaps/pull/38
- **Valeur historique :** élevée
- **Complexité historique :** moyenne

**Intention conservée.** Éviter de charger puis filtrer uniquement côté navigateur en proposant recherche textuelle, catégories, source et plage de dates côté API.

**État à réévaluer.** Une partie importante existe déjà (`q`, `category`, `source`, `start_from`, `start_to`). Après stabilisation, comparer le besoin restant aux performances réelles avant d'envisager FTS5, normalisation ou nouveaux filtres.

**Garde-fous.** Ne pas lancer avant stabilisation des contrats API, des tests de plage de dates et du modèle d'attributs.

## BACKLOG-FEAT-003 — Mode « événements à proximité de moi »

- **Décision : Différé après stabilisation**
- **Origine :** FEAT-003
- **Implémenté :** https://github.com/cochetquentin/EventMaps/pull/39
- **Valeur historique :** élevée
- **Complexité historique :** moyenne

**Intention conservée.** Trier ou filtrer les événements par distance après géolocalisation et afficher cette distance.

**Options historiques.** Calcul Haversine local pour un MVP ; endpoint géospatial et rayon pour une évolution plus complète.

**Garde-fous.** Préserver la vie privée, privilégier le calcul local par défaut et ne reprendre qu'après stabilisation du frontend et de son contrat API.

## BACKLOG-FEAT-005 — Métadonnées de source et page détail événement

- **Décision : Différé après stabilisation ; périmètre à réévaluer**
- **Origine :** FEAT-005
- **Implémenté :** https://github.com/cochetquentin/EventMaps/pull/40
- **Valeur historique :** moyenne
- **Complexité historique :** moyenne

**Intention conservée.** Mieux exposer les descriptions, liens officiels, accès, parking, politiques météo et autres données déjà collectées.

**État à réévaluer.** Le frontend possède déjà plusieurs mécanismes de détail ; vérifier le besoin utilisateur restant avant de créer un nouveau drawer ou une route partageable.

**Garde-fous.** Toute reprise dépend de la sécurité du rendu des données externes et de la stabilisation des attributs par source.

## BACKLOG-FEAT-006 — Ajouter une nouvelle source d'événements

- **Décision : Différé après stabilisation ; proposition historique partiellement réalisée**
- **Origine :** FEAT-006
- **Valeur historique :** élevée
- **Complexité historique :** grande

**Intention conservée.** Étendre la couverture avec une source supplémentaire en respectant le contrat `Event`, les droits d'utilisation et une stratégie de fixtures réelles.

**État à réévaluer.** Time Out Tokyo a été ajouté depuis l'ancien constat. Toute nouvelle source supplémentaire doit attendre la stabilisation des trois scrapers existants et être justifiée par sa valeur, ses conditions d'utilisation et son coût de maintenance.

**Garde-fous.** Ne pas reprendre avant la fin des tâches de fixtures réelles, de contrat des scrapers et de revue des droits/conditions de la source envisagée.
