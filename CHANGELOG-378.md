# Changelog — Issue #378

## Bandeau de reconnexion Lichess : rappel que la partie reste gérable sur lichess.org

Suite de l'étude #376 (lecture seule), qui concluait que la limitation « adversaire parti non réémis à la reconnexion » (point ouvert de #368) vient de Lichess, pas d'AlChess — aucune correction côté code possible. Solution la plus simple retenue : purement textuelle, sans aucune nouvelle logique.

Pendant une coupure réseau en partie Lichess, le bandeau `#lichess-reconnecting-banner` (clé i18n `lichess.reconnexion`) affichait seulement « Connexion à Lichess perdue, reconnexion… », sans aucune piste de repli pour l'utilisateur.

- `nicsoft/web/static/i18n/{fr,en,de}.json` : la clé `lichess.reconnexion` (déjà existante, aucune nouvelle clé) est complétée dans les trois langues par une courte phrase rappelant que la partie reste gérable directement sur lichess.org (jouer, réclamer, abandonner), indépendamment d'AlChess. Même modèle que la clé voisine `lichess.echiquier_perdu`.
- `nicsoft/web/templates/index.html` : texte de repli statique du bandeau mis à jour à l'identique (même id, même `data-i18n`, seul le texte change) pour rester synchronisé avec `fr.json`.
- `nicsoft/tests/test_issue378_lichess_reconnect_banner_text.py` (nouveau) : clé présente et non vide dans les trois locales, parité des clés entre fr/en/de, mention de « lichess.org » dans les trois langues, longueur bornée (bandeau court et lisible), bandeau HTML inchangé au-delà du texte (même id, même classe, même `data-i18n`, toujours masqué par défaut), fallback HTML synchronisé avec `fr.json`.

### Contraintes respectées

- Aucun fichier Python de `modes/lichess/` ni `core/game_manager_modes/lichess.py` modifié.
- Aucun changement de logique de réclamation, de nulle, ni de contournement de l'évènement `opponentGone` — purement textuel.
- Comportement d'apparition/disparition du bandeau inchangé (toujours piloté par `lichess_reconnecting`/`lichess_reconnected`, app.js non modifié).
- `CONTEXTE.md` inchangé (3535 caractères) : aucune règle/architecture/convention modifiée par cette tâche textuelle.
