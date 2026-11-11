"""
Teste la configuration du journal (issue #265) : la sortie stderr relayée
par python-chess (bannière de démarrage lc0/Maia) ne doit plus apparaître
dans le journal applicatif. On relève le niveau du logger "chess.engine"
à ERROR — les WARNING (dont la bannière de démarrage) sont filtrés, les
vraies erreurs internes à python-chess restent journalisées.
"""
import logging

import nicsoft.web.alchess as alchess


def test_chess_engine_logger_niveau_releve(tmp_path, monkeypatch):
    """_setup_logging() doit relever le logger 'chess.engine' au-dessus de WARNING."""
    monkeypatch.setattr(alchess, "LOG_FILE", tmp_path / "niclink.log")

    alchess._setup_logging()

    chess_engine_logger = logging.getLogger("chess.engine")
    assert chess_engine_logger.level == logging.ERROR
    assert not chess_engine_logger.isEnabledFor(logging.WARNING)
    assert chess_engine_logger.isEnabledFor(logging.ERROR)


def test_lichess_info_dans_le_fichier_autres_loggers_inchanges(tmp_path, monkeypatch):
    """
    Issue #312 : les lignes du mode Lichess ("niclink.lichess") doivent
    toujours être écrites dans le fichier de journal au niveau INFO, sans
    changer le niveau des autres loggers ("niclink.server" et consorts
    restent au niveau WARNING hérité du root — c'est l'abaissement du
    file_handler PARTAGÉ, pas celui d'un logger spécifique, qui avait
    l'effet de bord sur Werkzeug corrigé par cette issue).
    """
    monkeypatch.setattr(alchess, "LOG_FILE", tmp_path / "niclink.log")

    alchess._setup_logging()

    lichess_logger = logging.getLogger("niclink.lichess")
    server_logger = logging.getLogger("niclink.server")
    assert lichess_logger.level == logging.INFO
    assert server_logger.getEffectiveLevel() == logging.WARNING

    lichess_logger.info("ligne lichess visible")
    server_logger.info("ligne server invisible — niveau inchangé")
    server_logger.warning("ligne server visible — WARNING franchit toujours")

    contenu = alchess.LOG_FILE.read_text(encoding="utf-8")
    assert "ligne lichess visible" in contenu
    assert "ligne server invisible" not in contenu
    assert "ligne server visible" in contenu


def test_werkzeug_garde_un_handler_console_malgre_le_file_handler_abaisse(tmp_path, monkeypatch):
    """
    Issue #312 : werkzeug._internal._has_level_handler() ne regarde que
    l'attribut numérique .level des handlers accessibles depuis le logger
    "werkzeug" en remontant ses parents — un test satisfait par erreur une
    fois le file_handler partagé abaissé à INFO pour les lignes Lichess,
    ce qui empêchait Werkzeug d'ajouter son propre handler console
    ("Running on http://...", avertissement serveur de dev, "Press CTRL+C
    to quit" disparaissaient, y compris en usage interactif). _setup_logging()
    doit donc garantir elle-même un handler console sur "werkzeug".
    """
    monkeypatch.setattr(alchess, "LOG_FILE", tmp_path / "niclink.log")

    alchess._setup_logging()

    werkzeug_logger = logging.getLogger("werkzeug")
    assert werkzeug_logger.isEnabledFor(logging.INFO)
    assert any(
        isinstance(h, logging.StreamHandler) and h.level <= logging.INFO
        for h in werkzeug_logger.handlers
    )
