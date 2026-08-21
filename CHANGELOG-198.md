# Changelog — issue #198

## Fix — Drawer LLM Analyse de partie : champ texte invisible + markdown brut

- **Champ texte invisible** : le bouton `#analyse-llm-send-btn` héritait de `.btn { display:block; width:100% }` (défini dans `main.css`) sans override inline, et occupait donc la quasi-totalité de la ligne flex (`display:flex`) partagée avec l'input. Résultat mesuré (Chromium headless, viewport 1400px) : input réduit à **22×33px** contre 426×33px pour le bouton. Correction : ajout de `width:auto; flex-shrink:0;` dans le style inline du bouton — l'input passe à ~386px de large. `nicsoft/web/templates/index.html`.
- **Markdown brut affiché** : le drawer utilise `textContent` (pas de rendu HTML) mais recevait le texte brut du LLM (`**gras**`, `- item`, `# titre`). Ajout de `stripMarkdownForChat()` dans `app.js` (inspirée de `stripMarkdownForTts()` déjà présente pour l'Opening Explorer), appliquée sur `data.text` dans le handler `socket.on("analyse_llm_response", ...)` avant poussée dans `_analyseLlmHistory` et rendu de la bulle. Contrairement à la version TTS, les sauts de ligne sont préservés (bulle en `white-space:pre-wrap`) plutôt que collapsés en espaces. `nicsoft/web/static/app.js`.

Vérifié en Chromium headless (Playwright) : dimensions de l'input avant/après, et sortie de `stripMarkdownForChat()` sur un échantillon avec titres/gras/italique/listes.
