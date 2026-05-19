"""Backend hidapi Python pour Chessnut Air — remplace _niclink.so

Expose la même API que _niclink : connect, disconnect, get_fen,
set_all_leds, lights_out, set_led, beep, gameover_lights.
"""

import hid
import threading
import time

VENDOR_ID   = 0x2d80
PRODUCT_IDS = [0x8001, 0x8002, 0x8003]
USAGE_PAGE  = 0xFF00
WRITE_INTERVAL = 0.2  # secondes — identique au C++ (200ms)

# Mapping pièces — identique à ChessLink::toFen dans EasyLink.cpp
_PIECES = ['0', 'q', 'k', 'b', 'p', 'n', 'R', 'P', 'r', 'B', 'N', 'Q', 'K']

_dev: hid.device | None = None
_current_fen: str = ""
_led_status: list[int] = [0] * 8  # pattern LED courant en ordre USB (index 0 = rangée 8)
_write_lock = threading.Lock()
_last_write: float = 0.0


def _list_paths() -> list[bytes]:
    """Retourne les paths HID des Chessnut Air détectés."""
    paths = []
    for info in hid.enumerate(VENDOR_ID, 0):
        if info['product_id'] in PRODUCT_IDS and info.get('usage_page') == USAGE_PAGE:
            paths.append(info['path'])
    if not paths:
        # Fallback sans filtre usage_page (Linux hidraw ne l'expose pas toujours)
        for info in hid.enumerate(VENDOR_ID, 0):
            if info['product_id'] in PRODUCT_IDS:
                paths.append(info['path'])
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
    ouverture HID → sleep 2s → upload mode → beep → realtime mode.
    """
    global _dev
    paths = _list_paths()
    if not paths:
        raise RuntimeError("Chessnut Air introuvable (VID=0x2d80)")
    _dev = hid.device()
    _dev.open_path(paths[0])

    time.sleep(2)  # attente initialisation hardware (identique C++)
    _write(bytes([0x21, 0x01, 0x01]))  # upload mode — test de connexion
    _write(bytes([0x0b, 0x04, 0x02, 0x58, 0x00, 0xc8]))  # beep (600Hz, 200ms)
    _write(bytes([0x21, 0x01, 0x00]))  # realtime mode — envoi position en continu


def disconnect() -> None:
    """Repasse en upload mode et ferme la connexion HID."""
    global _dev
    if _dev is not None:
        try:
            _write(bytes([0x21, 0x01, 0x01]))  # upload mode avant fermeture
            _dev.close()
        except Exception:
            pass
        _dev = None


def get_fen() -> str:
    """Lit la position courante depuis l'échiquier USB.

    En mode realtime, le Chessnut Air envoie continuellement sa position.
    Retourne le dernier FEN valide reçu (ou "" si aucune donnée).
    """
    global _current_fen
    if _dev is None:
        return ""
    buf = _dev.read(256, timeout_ms=50)
    if buf and len(buf) > 1 and buf[0] == 0x01:
        fen = _decode_fen(bytes(buf))
        if fen:
            _current_fen = fen
    return _current_fen


def _decode_fen(data: bytes) -> str:
    """Décode les bytes USB en FEN board-only.

    Traduit fidèlement ChessLink::toFen() de EasyLink.cpp :
    64 cases encodées en 32 bytes (4 bits/pièce), 2 pièces par byte.
    i=0 = rangée 8, j=7..0 = fichier a..h.
    """
    if len(data) <= 32:
        return ""
    fen = ""
    empty = 0
    for i in range(8):
        for j in range(7, -1, -1):
            idx = (i * 8 + j) // 2 + 2
            piece_idx = (data[idx] & 0x0f) if j % 2 == 0 else (data[idx] >> 4)
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
