"""Backend hidapi Python pour Chessnut Air — remplace _niclink.so

Expose la même API que _niclink : connect, disconnect, get_fen,
set_all_leds, lights_out, set_led, beep, gameover_lights.
"""

import hid
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


def _write(data: bytes) -> None:
    """Écriture HID avec délai minimum entre deux écritures (idem C++ WRITE_INTERVAL)."""
    global _last_write
    with _write_lock:
        elapsed = time.time() - _last_write
        if elapsed < WRITE_INTERVAL:
            time.sleep(WRITE_INTERVAL - elapsed)
        if _dev is not None:
            _dev.write(data)
        _last_write = time.time()


def connect() -> None:
    """Connecte au Chessnut Air et passe en mode temps réel.

    Réplique la séquence de NicLink.cpp connect() :
    ouverture HID → sleep 2s → beep → realtime mode → attente premier FEN.

    Note : dans le C++ original, switchUploadMode() était appelé avant open_path(),
    donc c'était un no-op (b_write vérifie connectStatus). On ne l'envoie pas ici
    pour éviter un bip parasite causé par la commande de switch de mode.
    """
    global _dev, _current_fen, _connected_product_id, _connected
    paths = _list_paths()
    if not paths:
        raise RuntimeError("Chessnut Air introuvable (VID=0x2d80)")
    path, product_id = paths[0]
    _dev = hid.device()
    _dev.open_path(path)

    _connected_product_id = product_id
    _connected = True
    name = _PRODUCT_NAMES.get(product_id, "modèle inconnu")
    logger.info("Chessnut connecté : PID=0x%04x (%s)", product_id, name)

    time.sleep(2)  # attente initialisation hardware (identique C++)
    _write(bytes([0x0b, 0x04, 0x02, 0x58, 0x00, 0xc8]))  # beep (600Hz, 200ms)
    _write(bytes([0x21, 0x01, 0x00]))  # realtime mode — le plateau envoie sa position en continu

    # Attendre le premier paquet FEN valide (le plateau peut prendre ~600ms)
    # pour que driver.py lise un FEN non-vide dès la première tentative.
    for _ in range(30):  # jusqu'à 3s (30 × 100ms)
        buf = _dev.read(256, timeout_ms=100)
        if buf and len(buf) > 1:
            fen = _decode_fen(bytes(buf))
            if fen:
                _current_fen = fen
                break


def disconnect() -> None:
    """Repasse en upload mode et ferme la connexion HID."""
    global _dev, _connected
    if _dev is not None:
        try:
            _write(bytes([0x21, 0x01, 0x01]))  # upload mode avant fermeture
            _dev.close()
        except Exception:
            pass
        _dev = None
    _connected = False


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
    if not _connected or _dev is None:
        return False
    try:
        for info in hid.enumerate(VENDOR_ID, 0):
            if info['product_id'] in PRODUCT_IDS:
                return True
        _connected = False
        return False
    except Exception:
        return False


def get_fen() -> str:
    """Lit la position courante depuis l'échiquier USB.

    En mode realtime, le Chessnut Air envoie continuellement sa position.
    Retourne le dernier FEN valide reçu (ou "" si aucune donnée).
    Si la lecture USB échoue (plateau débranché en cours de session),
    réinitialise l'état de connexion sans lever d'exception.
    """
    global _current_fen, _dev, _connected
    if _dev is None:
        return ""
    try:
        buf = _dev.read(256, timeout_ms=50)
    except (OSError, IOError) as e:
        logger.warning("get_fen: erreur de lecture USB (plateau déconnecté ?) : %s", e)
        _dev = None
        _current_fen = ""
        _connected = False
        return ""
    if buf and len(buf) > 1:
        fen = _decode_fen(bytes(buf))
        if fen:
            _current_fen = fen
    return _current_fen


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
