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
import subprocess
import tempfile

logger = logging.getLogger("niclink.opening_explorer.tts")


VOICE_MAP_EDGE = {
    "fr": "fr-FR-DeniseNeural",
    "en": "en-GB-SoniaNeural",
    "de": "de-DE-KatjaNeural",
}
VOICE_MAP_ESPEAK = {"fr": "fr", "en": "en", "de": "de"}


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
    if not enabled or not text:
        return False
    if not check_internet():
        return False
    return _speak_edge(text, rate, language)
