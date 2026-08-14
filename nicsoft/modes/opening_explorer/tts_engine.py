"""
nicsoft/modes/opening_explorer/tts_engine.py — NicLink
Synthèse vocale des explications Opening Explorer via espeak-ng en
subprocess direct. pyttsx3 abandonné : le GC détruisait l'engine pendant
le callback espeak, provoquant des ReferenceError après un ou deux mots.
"""

import logging
import subprocess

logger = logging.getLogger("niclink.opening_explorer.tts")


VOICE_MAP = {"fr": "fr", "en": "en", "de": "de"}


def speak(text: str, rate: int = 150, enabled: bool = False, language: str = "fr") -> None:
    """Prononce `text` à voix haute si `enabled`, dans la langue `language`
    (voix espeak-ng correspondante si disponible). Bloquant — à appeler
    depuis un thread daemon, jamais depuis le thread principal.
    Erreur silencieuse (espeak-ng manquant, etc.).
    """
    if not enabled or not text:
        return
    lang = VOICE_MAP.get(language, "fr")
    try:
        subprocess.run(
            ["espeak-ng", "-v", lang, "-s", str(rate), text],
            timeout=60,
            check=False
        )
    except Exception as e:
        logger.warning(f"[TTS] Échec espeak-ng : {e}")
