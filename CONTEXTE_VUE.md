# CONTEXTE_VUE.md — Rôle Spec-Vue

Fiche de rôle pour le CCL spécialisé **Vue** (pattern Chef + Specs MVC, §15 du
BRIDGE_AGENT_DOC). Reflète la structure réelle vérifiée le 14 juillet 2026.

## Périmètre (dossiers dédiés)

- `nicsoft/web/templates/` — HTML
- `nicsoft/web/static/` — JS, CSS, i18n, pièces SVG

Toute issue routée `SPECS=vue` reste dans ce périmètre. Ne pas toucher à la
logique de jeu (`core/`, `engine/`) ni à la persistance.

## Fichiers clés

| Fichier | Rôle |
|---------|------|
| `templates/index.html` | Interface HTML unique (SPA mono-template, ~107 Ko) |
| `static/app.js` | Toute la logique JS frontend (~250 Ko) |
| `static/css/main.css` | Feuille de style unique |
| `static/i18n.js` + `static/i18n/{fr,en,de}.json` | Internationalisation |
| `static/pieces/` | 12 pièces SVG (wP…bK) style Lichess |
| `static/favicon.svg` | Icône |

## Conventions front en place

- **JS vanilla**, aucun framework (pas de React/Vue/jQuery), pas de bundler.
- **Pièces SVG Lichess** (`static/pieces/{w,b}{P,N,B,R,Q,K}.svg`).
- **i18n obligatoire** : jamais de libellé hardcodé. HTML → `data-i18n="cle"` ;
  JS → `t("cle")`. Toute clé ajoutée simultanément dans `fr/en/de.json`
  (allemand incertain → valeur anglaise en attendant). Cf. `I18N.md`.
- Communication temps réel via **SocketIO** : `sendAction({type: X})` côté JS ↔
  handler `on_action` côté Python (tout type doit avoir son `elif`).
