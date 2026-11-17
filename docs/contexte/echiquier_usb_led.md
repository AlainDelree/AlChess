# AlChess — Échiquier USB et LED

Lire avant toute tâche qui touche `nicsoft/niclink/driver.py`, `hid_backend.py`, `virtual_board.py`, ou toute pose de pattern LED.

- **USB** : un seul accès ouvert à la fois (`connect()` ferme l'ancien) ; chaque mode appelle `disconnect()` en fin de session ; la présence physique se lit par `hid.enumerate()`, indépendamment de la connexion.
- Polling `time.sleep()` ≥ 0.05 s (ne jamais monopoliser le GIL) ; threads LED toujours daemon, ne jamais bloquer la boucle de jeu sur les LEDs.
- **Convention LED** : indice i du tableau de rangées = rangée i+1 (`hid_backend.set_all_leds`) — un bug d'inversion (#340) a longtemps allumé le camp de l'utilisateur à la place de l'adversaire. Vérifier ce sens avant toute nouvelle pose de pattern. Détail : CHANGELOG.md (#340).
- Quirk usbhid requis (ThinkPad X1 Carbon Gen 7) : `/etc/modprobe.d/chessnut.conf` = `options usbhid quirks=0x2d80:0x8003:0x40`. Procédure complète : `INSTALLATION_ALCHESS.md` (sections 4b/4c).
