import pytest

from casino.payouts import Bankroll


def test_default_starting_balance():
    bank = Bankroll()
    assert bank.balance == 1000


def test_custom_starting_balance():
    bank = Bankroll(starting_balance=500)
    assert bank.balance == 500


def test_place_bet_deducts_balance_and_returns_amount():
    bank = Bankroll(starting_balance=100)
    amount = bank.place_bet(40)
    assert amount == 40
    assert bank.balance == 60


def test_place_bet_exceeding_balance_raises():
    bank = Bankroll(starting_balance=50)
    with pytest.raises(ValueError):
        bank.place_bet(51)
    # balance unchanged after failed bet
    assert bank.balance == 50


def test_place_bet_exact_balance_allowed():
    bank = Bankroll(starting_balance=50)
    amount = bank.place_bet(50)
    assert amount == 50
    assert bank.balance == 0


def test_resolve_push_returns_bet():
    bank = Bankroll(starting_balance=100)
    bank.place_bet(20)
    new_balance = bank.resolve("push", 20)
    assert new_balance == 100
    assert bank.balance == 100


def test_resolve_player_win_standard_payout():
    bank = Bankroll(starting_balance=100)
    bank.place_bet(20)
    # balance now 80; player wins standard (1:1) -> +20 (bet back) + 20 (winnings) = 120
    new_balance = bank.resolve("player", 20, player_blackjack=False)
    assert new_balance == 120
    assert bank.balance == 120


def test_resolve_player_win_blackjack_payout():
    bank = Bankroll(starting_balance=100)
    bank.place_bet(20)
    # balance now 80; blackjack pays 3:2 -> +20 (bet back) + 30 (1.5x winnings) = 130
    new_balance = bank.resolve("player", 20, player_blackjack=True)
    assert new_balance == 130
    assert bank.balance == 130


def test_resolve_dealer_win_keeps_bet_deducted():
    bank = Bankroll(starting_balance=100)
    bank.place_bet(20)
    # balance now 80; dealer wins, nothing added back
    new_balance = bank.resolve("dealer", 20)
    assert new_balance == 80
    assert bank.balance == 80


def test_resolve_player_blackjack_flag_defaults_to_false():
    bank = Bankroll(starting_balance=100)
    bank.place_bet(10)
    new_balance = bank.resolve("player", 10)
    assert new_balance == 110  # 90 + 10 + 10*1.0
