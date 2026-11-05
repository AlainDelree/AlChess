"""
Tests VirtualBoard — interface sans matériel.

Vérifie que VirtualBoard imite bien l'interface de NicLinkManager pour les
méthodes appelées par game_manager.py en fin de session (exercices, drill,
opening explorer), sans échiquier physique.
"""
from nicsoft.niclink.virtual_board import VirtualBoard


def test_disconnect_ne_leve_pas_erreur():
    """disconnect() doit être un no-op silencieux — pas d'AttributeError (issue #269)."""
    vb = VirtualBoard()
    vb.disconnect()
