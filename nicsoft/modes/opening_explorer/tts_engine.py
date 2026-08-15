"""
nicsoft/modes/opening_explorer/tts_engine.py — NicLink
Synthèse vocale des explications Opening Explorer, hybride :
si internet est disponible, edge-tts (voix neuronales Microsoft) parle
côté serveur ; sinon speak() ne fait rien et retourne False, laissant
le navigateur relayer via Web Speech API (voix système, meilleure
qu'espeak-ng sur Windows/Mac). espeak-ng reste disponible en dernier
recours mais n'est plus appelé automatiquement par speak().
pyttsx3 abandonné : le GC détruisait l'engine pendant le callback espeak,
provoquant des ReferenceError après un ou deux mots.
"""

import asyncio
import logging
import os
import re
import subprocess
import tempfile

logger = logging.getLogger("niclink.opening_explorer.tts")


VOICE_MAP_EDGE = {
    "fr": "fr-FR-DeniseNeural",
    "en": "en-GB-SoniaNeural",
    "de": "de-DE-KatjaNeural",
}
VOICE_MAP_ESPEAK = {"fr": "fr", "en": "en", "de": "de"}

PIECES_FR = {
    'N': 'Cavalier', 'C': 'Cavalier',
    'B': 'Fou',      'F': 'Fou',
    'R': 'Tour',     'T': 'Tour',
    'Q': 'Dame',     'D': 'Dame',
    'K': 'Roi',
}

_SAN_MOVE_RE = re.compile(r'\b([NBRKQCDFDT]?[a-h]?[1-8]?x?[a-h][1-8](?:=[NBRQKCDFDT])?[+#]?)\b')


def san_to_spoken_fr(san: str) -> str:
    """Convertit une notation SAN (ex. Cc3, Nc3, exd5, e8=Q) en texte parlé français."""
    san = san.strip()
    if san in ('O-O-O', '0-0-0'):
        return 'grand roque'
    if san in ('O-O', '0-0'):
        return 'petit roque'
    san_clean = re.sub(r'[+#!?]', '', san)
    ep = ' en passant' if san_clean.endswith('e.p.') else ''
    san_clean = san_clean.replace('e.p.', '').strip()
    promo = ''
    promo_match = re.search(r'=([NBRQKCDFDT])', san_clean)
    if promo_match:
        promo = ' promotion en ' + PIECES_FR.get(promo_match.group(1), '')
        san_clean = san_clean[:promo_match.start()]
    takes = 'x' in san_clean
    san_clean = san_clean.replace('x', '')
    piece = ''
    if san_clean and san_clean[0].upper() in PIECES_FR:
        piece = PIECES_FR[san_clean[0].upper()]
        san_clean = san_clean[1:]
    dest = san_clean[-2:] if len(san_clean) >= 2 else san_clean
    if piece:
        if takes:
            return f'{piece} prend en {dest}{promo}{ep}'
        return f'{piece} en {dest}{promo}{ep}'
    else:
        if takes:
            return f'pion prend en {dest}{promo}{ep}'
        return f'{dest}{promo}{ep}'


def strip_markdown(text: str) -> str:
    """Retire les marqueurs Markdown (titres, gras, italique) avant lecture TTS."""
    text = re.sub(r'#{1,6}\s*', '', text)
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = re.sub(r'__(.+?)__', r'\1', text)
    text = re.sub(r'\*(.+?)\*', r'\1', text)
    text = re.sub(r'_(.+?)_', r'\1', text)
    text = re.sub(r'\n+', ' ', text)
    return text.strip()


def check_internet() -> bool:
    """Test rapide (2s max) de connectivité, pour décider edge-tts vs Web Speech API."""
    try:
        import urllib.request
        urllib.request.urlopen("https://api.edge-tts.com", timeout=2)
        return True
    except Exception:
        pass
    # Fallback : ping un DNS public
    try:
        import socket
        socket.setdefaulttimeout(2)
        socket.socket().connect(("8.8.8.8", 53))
        return True
    except Exception:
        return False


def _speak_edge(text: str, rate: int, language: str) -> bool:
    """Essaie de parler via edge-tts. Retourne True si succès, False sinon."""
    try:
        import edge_tts

        voice = VOICE_MAP_EDGE.get(language, "fr-FR-DeniseNeural")
        # rate edge-tts : "+0%" = 150 mots/min ≈ normal
        # on convertit le rate (mots/min) en pourcentage relatif
        rate_pct = f"+{int((rate - 150) / 1.5)}%" if rate != 150 else "+0%"

        async def _run():
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                tmp = f.name
            try:
                communicate = edge_tts.Communicate(text, voice, rate=rate_pct)
                await communicate.save(tmp)
                subprocess.run(["mpg123", "-q", tmp], check=False, timeout=60)
            finally:
                try:
                    os.unlink(tmp)
                except Exception:
                    pass

        asyncio.run(_run())
        return True
    except Exception as e:
        logger.warning(f"[TTS] edge-tts échoué : {e}")
        return False


def _speak_espeak(text: str, rate: int, language: str) -> None:
    """Fallback espeak-ng."""
    lang = VOICE_MAP_ESPEAK.get(language, "fr")
    try:
        subprocess.run(
            ["espeak-ng", "-v", lang, "-s", str(rate), text],
            timeout=60,
            check=False,
        )
    except Exception as e:
        logger.warning(f"[TTS] espeak-ng échoué : {e}")


def speak(text: str, rate: int = 150, enabled: bool = False, language: str = "fr") -> bool:
    """Prononce `text` à voix haute côté serveur si `enabled` et si internet
    est disponible (edge-tts, voix neuronale). Bloquant — à appeler depuis un
    thread daemon, jamais depuis le thread principal.
    Retourne True si edge-tts a parlé, False sinon (pas d'internet ou échec
    edge-tts) — dans ce cas l'appelant doit basculer sur le Web Speech API
    côté navigateur (pas d'espeak-ng comme fallback serveur).
    """
    text = strip_markdown(text)
    if language == "fr" and text:
        text = _SAN_MOVE_RE.sub(lambda m: san_to_spoken_fr(m.group(1)), text)
    if not enabled or not text:
        return False
    if not check_internet():
        return False
    return _speak_edge(text, rate, language)
