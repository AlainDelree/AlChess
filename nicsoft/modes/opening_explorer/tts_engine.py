"""
nicsoft/modes/opening_explorer/tts_engine.py — NicLink
Synthèse vocale des explications Opening Explorer via edge-tts (voix
neuronales Microsoft, internet requis), avec fallback automatique sur
espeak-ng en subprocess direct si edge-tts échoue (pas d'internet, etc.).
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


def speak(text: str, rate: int = 150, enabled: bool = False, language: str = "fr") -> None:
    """Prononce `text` à voix haute si `enabled`, dans la langue `language`.
    Essaie d'abord edge-tts (voix neuronale, internet requis) puis bascule
    automatiquement sur espeak-ng si edge-tts échoue. Bloquant — à appeler
    depuis un thread daemon, jamais depuis le thread principal.
    Erreur silencieuse (ni edge-tts ni espeak-ng disponibles, etc.).
    """
    if not enabled or not text:
        return
    if not _speak_edge(text, rate, language):
        _speak_espeak(text, rate, language)
