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
