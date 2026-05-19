"""
test_hidapi_windows.py — Test de compatibilité hidapi sur Windows (et Linux)

Usage :
    pip install hidapi
    python test_hidapi_windows.py

Ne requiert PAS le reste du projet NicLink — fichier autonome.
Tester avec le Chessnut Air branché en USB.
"""

import sys
import time
import threading

# ── Constantes protocole ───────────────────────────────────────────────────────
VENDOR_ID   = 0x2d80
PRODUCT_IDS = [0x8001, 0x8002, 0x8003]
USAGE_PAGE  = 0xFF00

_PIECES = ['0', 'q', 'k', 'b', 'p', 'n', 'R', 'P', 'r', 'B', 'N', 'Q', 'K']

OK   = "✓"
FAIL = "✗"
SKIP = "—"

results = []

def check(label, ok, detail=""):
    sym = OK if ok else FAIL
    msg = f"  [{sym}] {label}"
    if detail:
        msg += f" — {detail}"
    print(msg)
    results.append((label, ok))

def section(title):
    print(f"\n{'─'*50}")
    print(f"  {title}")
    print(f"{'─'*50}")


# ── 1. Import hidapi ───────────────────────────────────────────────────────────
section("1. Import hidapi")
try:
    import hid
    check("import hid", True, f"version {getattr(hid, '__version__', '?')}")
except ImportError as e:
    check("import hid", False, str(e))
    print("\n  → Installer avec : pip install hidapi")
    sys.exit(1)


# ── 2. Énumération ────────────────────────────────────────────────────────────
section("2. Énumération USB")

all_devs = list(hid.enumerate(VENDOR_ID, 0))
check("Enumerate VID=0x2d80", len(all_devs) > 0,
      f"{len(all_devs)} interface(s) trouvée(s)")

if not all_devs:
    print("  → Vérifiez que l'échiquier est allumé et branché.")
    sys.exit(1)

for d in all_devs:
    pid    = d['product_id']
    page   = d.get('usage_page', 'N/A')
    path   = d.get('path', b'').decode(errors='replace') if isinstance(d.get('path'), bytes) else str(d.get('path', ''))
    serial = d.get('serial_number', '') or ''
    print(f"      PID=0x{pid:04x}  usage_page=0x{page:04x}  serial={serial!r}")
    print(f"      path={path[:80]}")

with_usage = [d for d in all_devs if d.get('usage_page') == USAGE_PAGE and d['product_id'] in PRODUCT_IDS]
without    = [d for d in all_devs if d['product_id'] in PRODUCT_IDS]

check("usage_page=0xFF00 visible", len(with_usage) > 0,
      f"{'OUI — filtre précis actif' if with_usage else 'NON — fallback sans filtre sera utilisé'}")
check("Au moins un PID reconnu (0x8001/8002/8003)", len(without) > 0)

target_devs = with_usage if with_usage else without
if not target_devs:
    check("Interface cible trouvée", False, "Aucun périphérique utilisable")
    sys.exit(1)

target_path = target_devs[0]['path']
check("Interface cible sélectionnée", True,
      f"PID=0x{target_devs[0]['product_id']:04x}  usage_page=0x{target_devs[0].get('usage_page', 0):04x}")


# ── 3. Connexion ──────────────────────────────────────────────────────────────
section("3. Connexion HID")

dev = None
try:
    dev = hid.device()
    dev.open_path(target_path)
    check("open_path()", True)
except Exception as e:
    check("open_path()", False, str(e))
    print("  → Sur Windows, vérifiez que l'échiquier n'est pas déjà ouvert par un autre processus.")
    sys.exit(1)

try:
    mfr  = dev.get_manufacturer_string() or ""
    prod = dev.get_product_string() or ""
    check("get_manufacturer_string()", True, repr(mfr))
    check("get_product_string()", True, repr(prod))
except Exception as e:
    check("Strings", False, str(e))

print("  → Attente 2s (initialisation hardware)...")
time.sleep(2)


# ── 4. Commandes d'écriture ────────────────────────────────────────────────────
section("4. Commandes USB (écriture)")

write_lock  = threading.Lock()
last_write  = 0.0
WRITE_INTERVAL = 0.2

def _write(data: bytes) -> bool:
    global last_write
    with write_lock:
        elapsed = time.time() - last_write
        if elapsed < WRITE_INTERVAL:
            time.sleep(WRITE_INTERVAL - elapsed)
        try:
            n = dev.write(data)
            last_write = time.time()
            return n >= 0
        except Exception as e:
            last_write = time.time()
            print(f"      ERREUR write: {e}")
            return False

# Bip 600Hz 200ms
ok = _write(bytes([0x0b, 0x04, 0x02, 0x58, 0x00, 0xc8]))
check("Beep (0x0b) — entendez-vous un bip ?", ok, f"{len(bytes([0x0b, 0x04, 0x02, 0x58, 0x00, 0xc8]))} bytes")

# Realtime mode
ok = _write(bytes([0x21, 0x01, 0x00]))
check("Realtime mode (0x21)", ok)

# LED — allumer e2 et e7 (cases centrales)
leds = [0x00] * 8
leds[6] = 0b00010000  # rangée 2 (index USB 6), colonne e
leds[1] = 0b00010000  # rangée 7 (index USB 1), colonne e
ok = _write(bytes([0x0a, 0x08] + leds))
check("LEDs ON e2+e7 (0x0a) — voyez-vous 2 LEDs allumées ?", ok)

time.sleep(2)

# Éteindre LEDs
ok = _write(bytes([0x0a, 0x08] + [0x00] * 8))
check("LEDs OFF (0x0a)", ok)


# ── 5. Lecture FEN ─────────────────────────────────────────────────────────────
section("5. Lecture FEN (temps réel)")

def _decode_fen(data: bytes) -> str:
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

print("  Lecture de 10 paquets (timeout 200ms chacun)...")
fen_ok  = False
last_fen = ""
packet_count = 0
for attempt in range(10):
    try:
        buf = dev.read(256, timeout_ms=200)
        if buf:
            packet_count += 1
            if buf[0] == 0x01:
                fen = _decode_fen(bytes(buf))
                if fen:
                    last_fen = fen
                    fen_ok = True
    except Exception as e:
        print(f"  ERREUR read: {e}")
        break

check("Paquets reçus", packet_count > 0, f"{packet_count}/10")
check("FEN décodé", fen_ok, last_fen[:40] if fen_ok else "aucun FEN valide")

INITIAL = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR"
if fen_ok:
    check("Position = position initiale", last_fen == INITIAL,
          "oui" if last_fen == INITIAL else f"non — {last_fen[:40]}")


# ── 6. Latence FEN ────────────────────────────────────────────────────────────
section("6. Latence (déplacez une pièce pendant le test)")

print("  Mesure sur 20 lectures à 50ms...")
times = []
for _ in range(20):
    t0 = time.perf_counter()
    try:
        buf = dev.read(256, timeout_ms=50)
        if buf and buf[0] == 0x01:
            _decode_fen(bytes(buf))
    except Exception:
        pass
    times.append((time.perf_counter() - t0) * 1000)

avg = sum(times) / len(times)
mx  = max(times)
check("Latence moyenne < 100ms", avg < 100, f"{avg:.1f}ms (max {mx:.1f}ms)")


# ── 7. Déconnexion ─────────────────────────────────────────────────────────────
section("7. Déconnexion")
try:
    _write(bytes([0x21, 0x01, 0x01]))  # upload mode avant fermeture
    dev.close()
    check("close()", True)
except Exception as e:
    check("close()", False, str(e))


# ── Résumé ─────────────────────────────────────────────────────────────────────
section("Résumé")
total = len(results)
passed = sum(1 for _, ok in results if ok)
print(f"\n  {passed}/{total} tests réussis")
if passed == total:
    print(f"\n  {OK} Compatibilité hidapi Windows OK — le portage peut commencer.")
else:
    failed = [label for label, ok in results if not ok]
    print(f"\n  {FAIL} Problèmes détectés :")
    for f in failed:
        print(f"    · {f}")
print()
