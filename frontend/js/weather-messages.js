// Base de messages météo — édite librement ce fichier pour ajouter des phrases.
//
// Chaque clé = une situation météo ; le widget en pioche une AU HASARD dans la liste.
// Pour enrichir : ajoute simplement des lignes dans le tableau voulu.
//
// Situations :
//   rainSoon → de la pluie est prévue plus tard dans la journée
//   rainNow  → il pleut en ce moment
//   hot      → il fait chaud (≥ 30°)
//   cold     → il fait froid (≤ 6°)
//   nice     → beau et doux (ciel dégagé, 15–28°)
//   cloudy   → gris / couvert / brouillard
//   default  → tous les autres cas
//
// Placeholder spécial (rainSoon uniquement) : {h} est remplacé par l'heure de pluie,
// ex. « 15h ». Mets-le où tu veux dans la phrase.

export const WEATHER_MESSAGES = {
  rainSoon: [
    'Pluie prévue vers {h} ☔ — prévois un plan en intérieur',
    'Averses annoncées vers {h} — musée ou café peut-être ?',
    'Ça va tomber vers {h} 🌧️ — garde un parapluie',
    'Pluie attendue vers {h} — profite du beau temps d’ici là ☀️',
  ],
  rainNow: [
    'Il pleut 🌧️ — parapluie obligatoire !',
    'Temps à rester au chaud ☕ — expo ou izakaya ?',
    'Pluie en cours — parfait pour un musée 🖼️',
    'Averse dehors — un bon ramen en attendant ? 🍜',
  ],
  hot: [
    'Grosse chaleur 🥵 — hydrate-toi bien !',
    'Il fait chaud — cherche l’ombre et bois de l’eau 💧',
    'Canicule — privilégie l’intérieur climatisé ❄️',
    'Chaud devant 🔥 — pense à la crème solaire',
  ],
  cold: [
    'Ça caille 🧣 — couvre-toi bien',
    'Froid glacial — un ramen bien chaud ? 🍜',
    'Brrr ❄️ — pense aux couches',
    'Petit froid — un onsen ce serait pas mal ♨️',
  ],
  nice: [
    'Temps idéal pour sortir 🌸 — profites-en !',
    'Grand beau ☀️ — direction l’extérieur !',
    'Journée parfaite pour flâner 🚶',
    'Ciel dégagé — parfait pour un parc 🌳',
  ],
  cloudy: [
    'Ciel gris ☁️ — parfait pour un musée',
    'Un peu couvert — expo ou café cosy ?',
    'Temps doux et nuageux — balade tranquille 🚶',
    'Nuageux — journée idéale pour du shopping 🛍️',
  ],
  default: [
    'Belle journée à Tokyo ✨',
    'Bonne exploration à Tokyo 🗼',
  ],
};
