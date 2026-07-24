# Guide complet de scraping — Articles "Événements et festivals" d'Ichiban Japan

> Site cible : \`ichiban-japan.com\`
> Catégorie source : \`https://ichiban-japan.com/category/japon/evenements-japon/\`
> Objectif : extraire, de façon fiable et universelle, les **événements individuels** listés à l'intérieur de chaque article (festivals, expositions, marchés aux puces, etc.).

Ce manuel n'explique pas *avec quel outil* scraper, mais **comment le HTML est construit**, quels sont les motifs récurrents, quelles sont les variations d'une page à l'autre, et comment raisonner pour bâtir un extracteur robuste qui ne casse pas quand une page diffère un peu.

---

## 1. Nature du site : ce qu'il faut comprendre avant tout

Le site est un **WordPress** utilisant l'éditeur **Gutenberg** (éditeur par blocs). C'est l'information la plus importante du guide, car elle explique **tout** le reste :

- Chaque bloc de texte est un élément avec une classe préfixée par \`wp-block-\` (ex : \`wp-block-paragraph\`, \`wp-block-heading\`, \`wp-block-image\`).
- Le contenu réel de l'article est **toujours** encapsulé dans un unique conteneur \`.entry-content\`.
- Les listes d'articles (pages catégorie) sont générées par le bloc natif \`wp-block-latest-posts\`.

**Conséquence pratique :** les classes CSS sont stables et standardisées par WordPress. Elles ne changent pas d'une page à l'autre (contrairement au *contenu*). C'est sur ces classes qu'il faut s'appuyer, jamais sur la position ou l'ordre des éléments.

**Piège n°1 — la fausse impression de chaos.** En lisant les pages, on a l'impression que « chaque page est très différente ». C'est vrai pour le **texte** (nombre d'événements, présence d'images, embeds Instagram, légendes…), mais **faux pour la structure**. Le squelette HTML est identique partout. Il faut donc scraper la *structure*, pas le *contenu*.

---

## 2. Les deux niveaux à scraper

Il y a deux types de pages, à traiter en deux étapes :

1. **Les pages de listing (catégorie)** → servent uniquement à **découvrir les URLs** des articles.
2. **Les pages d'article** → contiennent les **événements** eux-mêmes, qui sont la vraie donnée à extraire.

---

## 3. Niveau 1 — Découverte des URLs (pages catégorie)

### 3.1 Pagination

La catégorie est paginée avec un motif d'URL parfaitement prévisible :

- Page 1 : \`/category/japon/evenements-japon/\`
- Page 2 : \`/category/japon/evenements-japon/page/2/\`
- Page 3 : \`/category/japon/evenements-japon/page/3/\`
- etc. → \`/page/N/\`

Le bloc de pagination porte la classe \`.pagination\` (avec un lien « Suivant »). Pour connaître le nombre total de pages, lire les numéros présents dans ce bloc, **ou** simplement incrémenter \`N\` jusqu'à ce qu'une page ne renvoie plus de cartes.

### 3.2 Structure d'une carte d'article

Les articles listés ne sont **pas** dans des balises \`<article>\` (attention, c'est contre-intuitif). Ils sont dans une liste \`<ul>\` du bloc *Latest Posts* :

\`\`\`
div.entry-content
└── ul.wp-block-latest-posts__list.post-columns.post-columns-3.has-dates
    └── li.post-card                      ← une carte = un article
        ├── div.post-thumbnail-wrapper
        │   └── a.post-thumbnail-link      ← LIEN vers l'article (href)
        │       ├── img.featured-image.wp-post-image
        │       └── div.category-overlay    ← étiquette de catégorie (ex : "Tohoku", "Tokyo")
        └── div.post-content-wrapper
            ├── a.post-title-link           ← LIEN vers l'article (href) + titre
            │   └── div.post-title           ← titre de l'article
            ├── div.post-meta
            │   └── span.post-date           ← date de publication (ex : "20 juillet 2026")
            └── div.post-excerpt             ← court extrait
\`\`\`

**Sélecteurs clés pour le niveau 1 :**

| Donnée | Sélecteur | Remarque |
|---|---|---|
| Conteneur d'une carte | \`li.post-card\` | itérer dessus |
| URL de l'article | \`a.post-title-link\` (ou \`a.post-thumbnail-link\`) — attribut \`href\` | deux liens pointent vers la même URL |
| Titre | \`.post-title\` | texte |
| Catégorie affichée | \`.category-overlay\` | ex : Tokyo, Tohoku… |
| Date | \`span.post-date\` | format français « 20 juillet 2026 » |
| Extrait | \`.post-excerpt\` | tronqué |

Environ **24 cartes par page**.

### 3.3 Reconnaître les URLs d'articles pertinents

Les URLs d'articles sont des **slugs à la racine** du domaine, en minuscules, avec tirets, et se terminent par \`/\` :

\`\`\`
https://ichiban-japan.com/<slug>/
\`\`\`

Exemples réels : \`/festivals-tokyo-mai-2026/\`, \`/expositions-tokyo-juin-2026/\`, \`/marches-aux-puces-tokyo/\`, \`/festivals-ete-tohoku/\`.

Les slugs pertinents commencent le plus souvent par \`festivals-\`, \`expositions-\`, \`marches-\`. Filtrer aussi pour **exclure** les pages non-articles qui ont le même format d'URL : \`/boutique/\`, \`/a-propos/\`, \`/visite-guidee-tokyo/\`, etc. Le plus sûr est de ne garder que les liens **issus de \`li.post-card\`** sur les pages catégorie, plutôt que tous les liens de la page (le menu et le pied de page contiennent aussi des slugs).

---

## 4. Niveau 2 — Structure d'une page d'article

### 4.1 Métadonnées (le raccourci le plus fiable)

Avant même de parser le HTML visible, **chaque article expose un bloc JSON-LD schema.org** dans le \`<head>\` :

\`\`\`
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "Article",
  "headline": "...",           ← titre
  "description": "...",         ← chapô / intro
  "url": "...",
  "datePublished": "2026-04-30T11:27:00+02:00",
  "dateModified": "2026-05-31T10:26:22+02:00",
  "inLanguage": "fr-FR",
  "author": { "@type": "Person", "name": "Guigui", "url": "..." },
  "publisher": { ... }
}
\`\`\`

En plus, on trouve les métadonnées classiques **Open Graph** (\`og:title\`, \`og:description\`, \`og:image\`, \`og:url\`) et Twitter Card. **Toujours récupérer le titre, la description, les dates et l'URL depuis ces métadonnées** : c'est plus propre et plus stable que de lire le DOM visible.

> ⚠️ Attention : le JSON-LD décrit **l'article dans son ensemble**, pas chaque événement individuel. Pour les événements un par un, il faut parser le corps (section 4.3).

### 4.2 Squelette d'une page d'article

Tout le contenu utile est dans \`div.entry-content\`. Ordre typique des enfants directs :

\`\`\`
div.entry-content
├── div.breadcrumbs            ← fil d'Ariane : Ichiban Japan > Découvrir le Japon > Événements et festivals
├── div.post-thumbnail-container
│   └── img                     ← image d'en-tête (alt = titre de l'article)
├── h1                          ← titre de l'article
├── p.wp-block-paragraph        ← paragraphe d'introduction (chapô)
│
│   ─── DÉBUT DU MOTIF RÉPÉTÉ (un bloc par événement) ───
├── h2.wp-block-heading         ← NOM DE L'ÉVÉNEMENT + dates entre parenthèses
├── (optionnel) figure.wp-block-image  ← image + légende
├── (optionnel) iframe.instagram-media + <script>  ← embed Instagram
├── p.wp-block-paragraph        ← description de l'événement
├── p.wp-block-paragraph        ← BLOC D'INFOS structuré (voir 4.4)
│   ─── FIN DU MOTIF RÉPÉTÉ ───
│
└── p.wp-block-paragraph        ← paragraphe de conclusion + liens vers articles voisins
\`\`\`

### 4.3 Le motif répété : un événement = un \`<h2>\` + le contenu qui suit

**C'est le cœur du scraping.** Chaque événement de l'article correspond à un titre \`h2.wp-block-heading\`. Le nombre de \`<h2>\` = le nombre d'événements (44 pour l'article de mai, 24 pour les expositions de mai, 12 pour les marchés).

Le format du titre \`<h2>\` est très régulier :

\`\`\`
Nom de l'événement (dates)
\`\`\`
Exemples : « Fukagawa Ryujin Reitaisai (1er mai 2026) », « Sanja Matsuri (15-17 mai 2026) », « Craft Gyoza Fes 2026 (jusqu'au 6 mai 2026) ».

**Stratégie universelle d'extraction d'un événement :** parcourir les enfants de \`.entry-content\` ; à chaque \`h2.wp-block-heading\` rencontré, commencer un nouvel événement, puis rattacher tous les éléments suivants (paragraphes, figures, embeds) **jusqu'au prochain \`h2\`**. C'est le principe du « regroupement par en-tête » — beaucoup plus robuste que de supposer un nombre fixe de paragraphes par événement.

### 4.4 Le bloc d'infos structuré (le plus précieux)

Pour chaque événement, **le dernier paragraphe** avant le \`<h2>\` suivant est un bloc d'infos très régulier, encodé avec des \`<br>\` (pas de balises sémantiques) :

\`\`\`
<p class="wp-block-paragraph">
  <strong>Nom de l'événement</strong><br>
  Dates en texte libre<br>
  Lieu : <a href="…lien Google Maps ou site du lieu…">Nom du lieu</a> (quartier)<br>
  <a href="…lien officiel…">Site de l'événement</a>
</p>
\`\`\`

Décomposition des nœuds (dans l'ordre) :

| Ordre | Nœud | Contenu | Comment l'extraire |
|---|---|---|---|
| 1 | \`<strong>\` | Nom de l'événement | texte du \`<strong>\` |
| 2 | texte libre | Dates (« 1er mai 2026 », « Du 3 au 5 mai 2026 », « 2 et 3 mai 2026 ») | nœud texte après le 1er \`<br>\` |
| 3 | \`Lieu :\` + \`<a>\` + texte | Nom du lieu (lien) + quartier entre parenthèses | texte du lien = lieu ; le \`( )\` qui suit = quartier |
| 4 | \`<a>\` | Lien officiel — libellé « Site de l'événement » ou « Site officiel » | attribut \`href\` |

**Comment repérer ce paragraphe de façon fiable :** c'est le \`p.wp-block-paragraph\` qui **contient le motif \`Lieu :\`** (parfois \`Lieux :\` au pluriel quand il y a plusieurs sites). Filtrer les paragraphes sur la présence de cette étiquette est la méthode la plus robuste.

**Variations observées à gérer :**
- Le libellé du lien final varie : « Site de l'événement » (festivals, marchés) ou « Site officiel » (expositions). Ne jamais matcher sur ce libellé exact ; prendre plutôt **le dernier \`<a>\` du bloc**.
- Parfois le \`<br>\` est *à l'intérieur* du \`<strong>\` (\`<strong>Nom<br></strong>\`) au lieu d'après. Ne pas compter sur la position exacte des \`<br>\` ; se baser sur l'ordre logique : \`<strong>\` = nom, ligne suivante = dates, ligne « Lieu : » = lieu, dernier lien = site.
- Le lieu peut ne pas avoir de quartier entre parenthèses.
- Le champ « Lieu : » peut être « Lieux : » avec deux lieux.

### 4.5 Formats de dates (à normaliser côté extracteur)

Les dates dans les \`<h2>\` et dans le bloc d'infos sont en **français, en texte libre**. Plusieurs formes coexistent :

- Jour unique : « 1er mai 2026 », « 5 mai 2026 »
- Deux jours : « 2 et 3 mai 2026 »
- Intervalle : « Du 3 au 5 mai 2026 », « Du 25 mai au 14 juin 2026 »
- Fin seulement : « jusqu'au 6 mai 2026 » (le titre) / « Du 29 avril au 6 mai 2026 » (le bloc infos)

Le **bloc d'infos (4.4) contient généralement la date la plus complète** (avec date de début), tandis que le \`<h2>\` peut n'afficher que « jusqu'au … ». Préférer la date du bloc d'infos.

### 4.6 Images et légendes

Les images intégrées au fil du texte sont des \`figure.wp-block-image\` contenant :
- un \`img\` avec une classe \`wp-image-XXXXX\` (ID interne WordPress) ;
- une légende optionnelle \`figcaption\` (ex : « Le tramway aux roses à Otsuka. », parfois avec crédit photo « © … »).

L'image d'en-tête de l'article (différente) est dans \`div.post-thumbnail-container\`, et son attribut \`alt\` reprend le titre de l'article.

### 4.7 Embeds Instagram (bruit à ignorer)

Beaucoup d'événements ont un embed Instagram : \`iframe.instagram-media\` (ou \`blockquote.instagram-media\`) suivi d'un \`<script>\`. Il y en avait **34** dans l'article de mai. Ils n'apportent pas de donnée textuelle exploitable : **les ignorer** lors du regroupement par \`<h2>\`, tout en sachant qu'ils s'intercalent entre le titre et la description.

---

## 5. Récapitulatif des sélecteurs (aide-mémoire)

**Page catégorie :**
\`\`\`
Cartes ............... li.post-card
URL article .......... li.post-card a.post-title-link   [href]
Titre ................ li.post-card .post-title
Date ................. li.post-card span.post-date
Catégorie ............ li.post-card .category-overlay
Extrait .............. li.post-card .post-excerpt
Pagination ........... .pagination  → /category/japon/evenements-japon/page/N/
\`\`\`

**Page article :**
\`\`\`
Conteneur contenu .... div.entry-content
Métadonnées .......... script[type="application/ld+json"]  (+ meta og:*)
Fil d'Ariane ......... .breadcrumbs
Titre article ........ .entry-content h1
Chapô ................ 1er .entry-content p.wp-block-paragraph
UN ÉVÉNEMENT ......... chaque h2.wp-block-heading  → regrouper jusqu'au h2 suivant
   Nom ............... texte du <strong> du bloc infos (ou du <h2>)
   Dates ............. bloc infos (ligne après le nom) ; sinon parenthèses du <h2>
   Lieu .............. p contenant "Lieu :" → texte du 1er <a> ; quartier = ( ) qui suit
   Site officiel ..... dernier <a> du bloc infos  [href]
   Description ....... p.wp-block-paragraph sans "Lieu :"
   Image ............. figure.wp-block-image (img + figcaption)
Bruit à ignorer ...... iframe.instagram-media, blockquote.instagram-media, script
\`\`\`

---

## 6. Méthodologie robuste (principes universels)

1. **S'ancrer sur les classes WordPress, jamais sur la position.** Les classes \`wp-block-*\`, \`entry-content\`, \`post-card\` sont stables ; l'ordre et le nombre d'éléments varient.
2. **Regrouper par en-tête (\`<h2>\`)**, pas par comptage. C'est ce qui absorbe les variations (image présente ou non, embed présent ou non, 1 ou 2 paragraphes de description).
3. **Détecter le bloc d'infos par son contenu** (« Lieu : ») plutôt que par sa position dans la séquence.
4. **Prendre le dernier lien du bloc d'infos** comme site officiel, quel que soit son libellé.
5. **Privilégier le JSON-LD / Open Graph** pour les métadonnées de l'article (titre, description, dates, auteur, image).
6. **Normaliser les dates françaises** en aval (jour unique / deux jours / intervalle / « jusqu'au »).
7. **Ignorer le bruit** : embeds Instagram, scripts, menu, sidebar (« Articles recommandés », « Recherche », zone de commentaires).
8. **Prévoir les cas dégénérés** : \`<br>\` dans le \`<strong>\`, « Lieux : » au pluriel, absence de quartier, absence d'image, absence de lien.
9. **Respecter le site** : throttling entre requêtes, lecture du \`robots.txt\`, pas de charge inutile.

---

## 7. Schéma de données recommandé (sortie)

Pour chaque **article** : \`url\`, \`titre\`, \`description\`, \`date_publication\`, \`date_modification\`, \`auteur\`, \`image_entete\`, \`ville/zone\` (déduite du slug ou de \`.category-overlay\`), et une liste d'**événements**.

Pour chaque **événement** : \`nom\`, \`dates_texte\` (brut), \`date_debut\`/\`date_fin\` (normalisées), \`lieu\`, \`quartier\`, \`url_officielle\`, \`description\`, \`image\` (+ légende, + crédit si présent).

---

*Fin du guide. Structure vérifiée sur les articles « festivals », « expositions » et « marchés aux puces » — le squelette est identique sur les trois.*
