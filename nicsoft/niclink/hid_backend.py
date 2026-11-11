"""Backend hidapi Python pour Chessnut Air — remplace _niclink.so

Expose la même API que _niclink : connect, disconnect, get_fen,
set_all_leds, lights_out, set_led, beep, gameover_lights.
"""

import hid
import inspect
import logging
import threading
import time

logger = logging.getLogger(__name__)

VENDOR_ID   = 0x2d80
PRODUCT_IDS = [0x8001, 0x8002, 0x8003, 0x8202, 0x8501]  # 8003=Air, 8202=Air Plus, 8501=Chessnut Go
USAGE_PAGE  = 0xFF00
WRITE_INTERVAL = 0.2  # secondes — identique au C++ (200ms)

# Mapping PID → nom lisible (pour les logs de diagnostic)
_PRODUCT_NAMES = {
    0x8001: "Chessnut (8001)",
    0x8002: "Chessnut (8002)",
    0x8003: "Chessnut Air",
    0x8202: "Chessnut Air Plus",
    0x8501: "Chessnut Go",
}

# Mapping pièces — identique à ChessLink::toFen dans EasyLink.cpp
_PIECES = ['0', 'q', 'k', 'b', 'p', 'n', 'R', 'P', 'r', 'B', 'N', 'Q', 'K']

_dev: hid.device | None = None
_current_fen: str = ""
_led_status: list[int] = [0] * 8  # pattern LED courant en ordre USB (index 0 = rangée 8)
_write_lock = threading.Lock()
_last_write: float = 0.0
_connected_product_id: int | None = None
_connected: bool = False  # True entre un connect() réussi et une erreur de lecture/un disconnect()

# Protège les écritures de _dev/_connected/_connected_product_id : connect(),
# get_fen() et disconnect() peuvent s'exécuter sur des fils différents (ex. un
# fen_reader de session précédente encore vivant pendant qu'une nouvelle
# connexion s'établit — issue #292). connect() et get_fen() travaillent sur une
# référence locale au périphérique pendant leurs I/O (potentiellement lentes ou
# bloquantes) et ne touchent la variable partagée que sous ce verrou, le temps
# d'une affectation — jamais pendant un appel USB.
_state_lock = threading.Lock()

# Sérialise les essais de connexion : si une reconnexion automatique (mode
# Lichess, issue #314) et un clic manuel sur "Connecter" tombent au même
# instant, un seul connect() s'exécute à la fois — le second attend son tour
# plutôt que de fermer un handle que l'autre vient juste d'ouvrir (#292).
_connect_lock = threading.Lock()

# Diagnostic des erreurs de lecture répétées (issue #314) : un même incident
# (plusieurs fils de lecture en échec sur le même périphérique, ou plusieurs
# échecs avant qu'un connect() ne le remplace) ne produit qu'un seul
# avertissement — les répétitions sont comptées et rapportées à la
# reconnexion suivante.
_read_error_lock = threading.Lock()
_read_error_active_dev: "hid.device | None" = None
_read_error_count: int = 0


def _caller_info(depth: int = 2) -> str:
    """Nom "module.fonction" de l'appelant de la fonction appelant ce
    helper — utilisé pour journaliser l'origine des ouvertures, fermetures
    et remises à zéro de la connexion (issue #314, diagnostic de la cause
    d'une déconnexion). `depth=2` cible l'appelant de la fonction qui a
    elle-même appelé `_caller_info()` directement."""
    try:
        frame = inspect.stack()[depth]
        module = inspect.getmodule(frame.frame)
        module_name = module.__name__ if module else frame.filename
        return f"{module_name}.{frame.function}"
    except (IndexError, ValueError):
        return "?"


def _log_read_error(dev: "hid.device | None", exc: Exception) -> None:
    """Journalise une erreur de lecture USB une seule fois par incident.

    Deux fils de lecture (ex. le fen_reader de driver.py et une attente
    Lichess qui appelle get_fen() directement) peuvent échouer au même
    instant sur le même périphérique — un seul avertissement est émis, les
    échecs suivants du même incident sont comptés silencieusement et
    rapportés à la prochaine connexion réussie (voir connect())."""
    global _read_error_active_dev, _read_error_count
    with _read_error_lock:
        if _read_error_active_dev is dev:
            _read_error_count += 1
            return
        _read_error_active_dev = dev
        _read_error_count = 1
    err_code = getattr(exc, "errno", None)
    logger.warning(
        "get_fen: erreur de lecture USB (plateau déconnecté ?) : %s [%s, code=%s]",
        exc, type(exc).__name__, err_code,
    )


def _list_paths() -> list[tuple[bytes, int]]:
    """Retourne les (path, product_id) HID des Chessnut Air détectés."""
    paths = []
    for info in hid.enumerate(VENDOR_ID, 0):
        if info['product_id'] in PRODUCT_IDS and info.get('usage_page') == USAGE_PAGE:
            paths.append((info['path'], info['product_id']))
    if not paths:
        # Fallback sans filtre usage_page (Linux hidraw ne l'expose pas toujours)
        for info in hid.enumerate(VENDOR_ID, 0):
            if info['product_id'] in PRODUCT_IDS:
                paths.append((info['path'], info['product_id']))
    return paths


def _write_to(dev: "hid.device | None", data: bytes) -> None:
    """Écriture HID sur une référence locale, avec délai minimum entre deux
    écritures (idem C++ WRITE_INTERVAL). Ne touche pas la variable partagée _dev."""
    global _last_write
    with _write_lock:
        elapsed = time.time() - _last_write
        if elapsed < WRITE_INTERVAL:
            time.sleep(WRITE_INTERVAL - elapsed)
        if dev is not None:
            dev.write(data)
        _last_write = time.time()


def _write(data: bytes) -> None:
    """Écriture HID sur le périphérique courant (_dev)."""
    with _state_lock:
        dev = _dev
    _write_to(dev, data)


def connect() -> None:
    """Connecte au Chessnut Air et passe en mode temps réel.

    Réplique la séquence de NicLink.cpp connect() :
    ouverture HID → sleep 2s → beep → realtime mode → attente premier FEN.

    Note : dans le C++ original, switchUploadMode() était appelé avant open_path(),
    donc c'était un no-op (b_write vérifie connectStatus). On ne l'envoie pas ici
    pour éviter un bip parasite causé par la commande de switch de mode.

    Travaille sur une référence locale au périphérique (`dev`) du début à la
    fin : un fil de lecture (get_fen()) ou une déconnexion (disconnect()) d'une
    session précédente, encore vivants en parallèle, peuvent librement remettre
    la variable partagée _dev à None sans jamais perturber cette connexion en
    cours — elle ne lit/écrit `dev` qu'après l'avoir publiée dans l'état partagé,
    une fois la connexion établie (issue #292 : plus d'AttributeError sur un
    _dev redevenu None pendant l'attente du premier paquet).

    Sérialisée par `_connect_lock` (issue #314) : une reconnexion automatique
    (mode Lichess) et un clic manuel sur "Connecter" ne peuvent jamais
    s'exécuter en même temps — un seul essai de connexion à la fois.
    """
    global _dev, _current_fen, _connected_product_id, _connected, _read_error_count
    caller = _caller_info()
    with _connect_lock:
        logger.info("connect: ouverture demandée (appelant=%s)", caller)
        paths = _list_paths()
        if not paths:
            raise RuntimeError("Chessnut Air introuvable (VID=0x2d80)")
        path, product_id = paths[0]
        # Fermer la connexion déjà ouverte (ex. vérification du démarrage) avant d'en ouvrir une
        # nouvelle : le périphérique n'accepte qu'un seul handle à la fois (OSError « open failed »).
        with _state_lock:
            old_dev = _dev
            _dev = None
            _connected = False
        if old_dev is not None:
            logger.info("connect: fermeture de l'ancien handle avant nouvelle ouverture (appelant=%s)", caller)
            try:
                old_dev.close()
            except (OSError, IOError, ValueError) as e:
                logger.debug("connect: fermeture de l'ancien handle échouée : %s", e)
        dev = hid.device()
        try:
            dev.open_path(path)

            time.sleep(2)  # attente initialisation hardware (identique C++)
            _write_to(dev, bytes([0x0b, 0x04, 0x02, 0x58, 0x00, 0xc8]))  # beep (600Hz, 200ms)
            _write_to(dev, bytes([0x21, 0x01, 0x00]))  # realtime mode — le plateau envoie sa position en continu

            # Attendre le premier paquet FEN valide (le plateau peut prendre ~600ms)
            # pour que driver.py lise un FEN non-vide dès la première tentative.
            fen = ""
            for _ in range(30):  # jusqu'à 3s (30 × 100ms)
                buf = dev.read(256, timeout_ms=100)
                if buf and len(buf) > 1:
                    decoded = _decode_fen(bytes(buf))
                    if decoded:
                        fen = decoded
                        break
        except (OSError, IOError, ValueError) as e:
            # Connexion perdue pendant l'établissement (plateau débranché juste après
            # l'ouverture, ou pendant le handshake) — jamais d'AttributeError, toujours
            # l'exception que les lanceurs de mode savent déjà afficher comme
            # "échiquier non détecté" (NicLinkManager.__init__ attrape RuntimeError).
            try:
                dev.close()
            except (OSError, IOError, ValueError):
                pass  # best-effort — le plateau peut déjà être débranché
            _reset_state()
            raise RuntimeError("Chessnut Air déconnecté pendant la connexion") from e

        with _state_lock:
            _dev = dev
            _current_fen = fen
            _connected_product_id = product_id
            _connected = True
        name = _PRODUCT_NAMES.get(product_id, "modèle inconnu")
        if _read_error_count > 1:
            logger.info(
                "connect: reconnexion après %d échecs de lecture consécutifs (appelant=%s)",
                _read_error_count, caller,
            )
        _read_error_count = 0
        logger.info("connect: Chessnut connecté : PID=0x%04x (%s), appelant=%s", product_id, name, caller)


def _reset_state() -> None:
    """Remet l'état partagé du module à zéro (après un échec de connexion),
    pour qu'un nouvel essai (y compris via le bouton de reconnexion) reparte
    d'un état propre sans redémarrer l'application."""
    global _dev, _current_fen, _connected_product_id, _connected
    logger.info("_reset_state: remise à zéro de la connexion (appelant=%s)", _caller_info())
    with _state_lock:
        _dev = None
        _current_fen = ""
        _connected_product_id = None
        _connected = False


def disconnect() -> None:
    """Repasse en upload mode et ferme la connexion HID.

    Récupère la référence partagée puis la remet à None sous verrou avant de
    faire l'I/O (potentiellement lente) sur la référence locale : un get_fen()
    concurrent ne peut plus jamais voir une référence à moitié fermée.
    """
    global _dev, _connected
    caller = _caller_info()
    logger.info("disconnect: fermeture demandée (appelant=%s)", caller)
    with _state_lock:
        dev = _dev
        _dev = None
        _connected = False
    if dev is not None:
        try:
            _write_to(dev, bytes([0x21, 0x01, 0x01]))  # upload mode avant fermeture
            dev.close()
            logger.info("disconnect: connexion fermée (appelant=%s)", caller)
        except (OSError, IOError, ValueError):
            pass  # best-effort avant déconnexion — le plateau peut déjà être débranché
            # (ValueError('not open') : hidapi/hid.pyx lève ValueError, pas OSError,
            # si le handle a déjà été fermé par un autre thread — course possible ici)


def is_connected() -> bool:
    """True si le plateau est actuellement considéré connecté (HID ouvert et lisible)."""
    return _connected


def check_physically_present() -> bool:
    """Vérifie si un Chessnut est encore visible dans le sous-système USB.

    Contrairement à get_fen(), qui sur Linux ne détecte pas un débranchement
    (le read() timeout silencieusement au lieu de lever une OSError), cette
    fonction interroge directement hid.enumerate() pour confirmer la présence
    physique du périphérique.
    """
    global _connected
    try:
        for info in hid.enumerate(VENDOR_ID, 0):
            if info['product_id'] in PRODUCT_IDS:
                return True
        _connected = False
        return False
    except Exception as e:
        logger.debug(f"check_physically_present: hid.enumerate() a échoué : {e}")
        return False


def get_fen() -> str:
    """Lit la position courante depuis l'échiquier USB.

    En mode realtime, le Chessnut Air envoie continuellement sa position.
    Retourne le dernier FEN valide reçu (ou "" si aucune donnée).
    Si la lecture USB échoue (plateau débranché en cours de session),
    réinitialise l'état de connexion sans lever d'exception.

    Travaille sur une référence locale (`dev`), capturée sous verrou puis lue
    hors verrou — l'opération USB peut bloquer jusqu'à 50ms sans retenir
    quiconque appellerait connect()/disconnect() entre-temps. Si la lecture
    échoue, l'état partagé n'est remis à zéro que s'il référence encore CE
    même périphérique : un fil de lecture d'une session abandonnée ne peut
    alors jamais écraser une connexion plus récente déjà établie (issue #292).
    """
    global _current_fen
    with _state_lock:
        dev = _dev
    if dev is None:
        return ""
    try:
        buf = dev.read(256, timeout_ms=50)
    except (OSError, IOError, ValueError) as e:
        # ValueError('not open') : hidapi/hid.pyx lève ValueError, pas OSError,
        # quand le handle a déjà été fermé par un autre thread (course avec disconnect()).
        _log_read_error(dev, e)
        _reset_state_if_current(dev)
        _current_fen = ""
        return ""
    if buf and len(buf) > 1:
        fen = _decode_fen(bytes(buf))
        if fen:
            _current_fen = fen
    return _current_fen


def _reset_state_if_current(dev: "hid.device | None") -> None:
    """Remet _dev/_connected à zéro seulement si _dev est toujours `dev`.

    Évite qu'une erreur de lecture tardive, provenant d'un fil de lecture
    d'une session déjà abandonnée, n'efface la référence d'une connexion plus
    récente établie entre-temps par connect().
    """
    global _dev, _connected
    caller = _caller_info()
    with _state_lock:
        if _dev is dev:
            _dev = None
            _connected = False
            is_current = True
        else:
            is_current = False
    if is_current:
        logger.info("_reset_state_if_current: remise à zéro (périphérique courant, appelant=%s)", caller)
    else:
        logger.debug("_reset_state_if_current: ignoré (périphérique déjà remplacé, appelant=%s)", caller)


def _decode_fen(data: bytes) -> str:
    """Décode les bytes USB en FEN board-only.

    Traduit fidèlement ChessLink::toFen() de EasyLink.cpp :
    64 cases encodées en 32 bytes (4 bits/pièce), 2 pièces par byte.
    i=0 = rangée 8, j=7..0 = fichier a..h.
    Fonctionne sur Linux (report ID 0x01) et Windows (0x01 ou 0x2a).
    """
    if len(data) < 34:  # besoin de 2 octets header + 32 octets FEN (idx max = 33)
        logger.debug(
            "_decode_fen: paquet trop court (%d octets, 34 requis) — premiers octets : %s",
            len(data), data[:8].hex(),
        )
        return ""
    i = j = idx = None
    try:
        fen = ""
        empty = 0
        for i in range(8):
            for j in range(7, -1, -1):
                idx = (i * 8 + j) // 2 + 2
                piece_idx = (data[idx] & 0x0f) if j % 2 == 0 else (data[idx] >> 4)
                if piece_idx >= len(_PIECES):
                    return ""
                piece = _PIECES[piece_idx]
                if piece == '0':
                    empty += 1
                else:
                    if empty > 0:
                        fen += str(empty)
                        empty = 0
                    fen += piece
            if empty > 0:
                fen += str(empty)
            if i < 7:
                fen += "/"
            empty = 0
        return fen
    except Exception as e:
        value = data[idx] if idx is not None and idx < len(data) else "?"
        logger.debug(
            "_decode_fen: exception à i=%s j=%s data[idx]=%s : %s", i, j, value, e,
        )
        return ""


def lights_out() -> None:
    """Éteint toutes les LEDs."""
    global _led_status
    _led_status = [0] * 8
    _write(bytes([0x0a, 0x08] + _led_status))


def set_all_leds(r1: str, r2: str, r3: str, r4: str,
                 r5: str, r6: str, r7: str, r8: str) -> None:
    """Allume un pattern LED. r1..r8 = strings 8 bits pour rangées 1 à 8.

    L'ordre USB est inversé (rangée 8 en premier) — identique à setAllLEDs C++.
    """
    global _led_status
    # C++ setAllLEDs stocke [rank8, rank7, ..., rank1] dans ledStatus[0..7]
    rows = [r8, r7, r6, r5, r4, r3, r2, r1]
    _led_status = [int(r, 2) for r in rows]
    _write(bytes([0x0a, 0x08] + _led_status))


def set_led(x: int, y: int, val: bool) -> None:
    """Modifie un seul LED en conservant le pattern courant.

    x, y : 0-7, identique à la signature C++ setLed(uint8_t x, uint8_t y, bool).
    """
    global _led_status
    if not (0 <= x <= 7 and 0 <= y <= 7):
        return
    if val:
        _led_status[x] |= (1 << y)
    else:
        _led_status[x] &= ~(1 << y)
    _write(bytes([0x0a, 0x08] + _led_status))


def beep(freq: int = 600, duration: int = 200) -> None:
    """Déclenche un bip sur l'échiquier."""
    _write(bytes([0x0b, 0x04, freq >> 8, freq & 0xff, duration >> 8, duration & 0xff]))


def gameover_lights() -> None:
    """Affiche le pattern 'game over' sur les LEDs (cadre + centre)."""
    lights_out()
    set_all_leds(
        "11111111", "10000001", "10111101", "10100101",
        "10100101", "10111101", "10000001", "11111111",
    )
