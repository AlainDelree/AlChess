from nicsoft.modes.humain.human import (
    normalize_player_name,
    find_existing_player,
)

def test_normalize_player_name():
    assert normalize_player_name(" Alain ") == "alain"
    assert normalize_player_name("ALAIN") == "alain"
    assert normalize_player_name("  Jean   Pierre  ") == "jean pierre"

def test_find_existing_player_case_insensitive():
    players = ["Alain", "Jessica", "Roger"]
    assert find_existing_player(players, "alain") == "Alain"
    assert find_existing_player(players, "  JESSICA ") == "Jessica"
    assert find_existing_player(players, "Pascal") is None
