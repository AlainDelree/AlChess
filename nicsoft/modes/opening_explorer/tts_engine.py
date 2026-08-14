"""
nicsoft/modes/opening_explorer/tts_engine.py — NicLink
Synthèse vocale des explications Opening Explorer via pyttsx3 (backend
espeak-ng sur Linux). Aucun singleton global : pyttsx3 est instable en
mode multi-thread si le moteur est partagé entre appels.
"""

import logging

logger = logging.getLogger("niclink.opening_explorer.tts")


def speak(text: str, rate: int = 150, enabled: bool = False) -> None:
    """Prononce `text` à voix haute si `enabled`. Bloquant — à appeler
    depuis un thread daemon, jamais depuis le thread principal.
    Erreur silencieuse (moteur TTS absent, espeak-ng manquant, etc.).
    """
    if not enabled or not text:
        return
    try:
        import pyttsx3
        engine = pyttsx3.init()
        engine.setProperty("rate", rate)
        engine.say(text)
        engine.runAndWait()
    except Exception as e:
        logger.warning(f"[TTS] Échec synthèse vocale : {e}")
