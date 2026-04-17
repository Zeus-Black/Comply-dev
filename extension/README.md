# Comply — Extension Navigateur

Posez vos questions directement sur Notion, Google Drive, ou n'importe quelle page web.

## Installation (Chrome / Edge)

1. Aller dans `chrome://extensions/`
2. Activer **Mode développeur** (coin supérieur droit)
3. Cliquer **Charger l'extension non empaquetée**
4. Sélectionner ce dossier `extension/`

## Configuration

1. Cliquer sur l'icône Comply dans la barre d'outils
2. Cliquer l'engrenage ⚙
3. Saisir l'URL de votre API Comply (ex: `http://localhost:8000` ou votre domaine)
4. Enregistrer

## Fonctionnement

- **Sur Notion** : l'extension lit automatiquement le contenu de la page ouverte et l'utilise comme contexte
- **Sur Google Docs/Drive** : même comportement
- **Partout ailleurs** : vous pouvez poser des questions générales sur les JE

Le bouton **Utiliser / Désactivé** permet d'activer ou désactiver l'injection du contexte de la page dans vos questions.

## Pages supportées automatiquement

- `notion.so`, `*.notion.site`
- `docs.google.com`, `drive.google.com`
- `*.junior-entreprises.com`

Sur les autres pages, l'extension fonctionne toujours mais sans extraction automatique de contenu.
