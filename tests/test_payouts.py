import pytest

from casino.payouts import Bankroll


def test_place_bet_deducts_balance():
    bankroll = Bankroll(starting_balance=1000)
    bankroll.place_bet(100)
    assert bankroll.balance == 900


def test_place_bet_rejects_bet_over_balance():
    bankroll = Bankroll(starting_balance=100)
    with pytest.raises(ValueError):
        bankroll.place_bet(200)


def test_resolve_player_win_standard_payout():
    bankroll = Bankroll(starting_balance=1000)
    bankroll.place_bet(100)
    bankroll.resolve("player", 100)
    assert bankroll.balance == 1100  # -100 bet, +200 (bet returned + 1:1 winnings)


def test_resolve_player_blackjack_payout():
    bankroll = Bankroll(starting_balance=1000)
    bankroll.place_bet(100)
    bankroll.resolve("player", 100, player_blackjack=True)
    assert bankroll.balance == 1150  # -100 bet, +250 (bet returned + 3:2 winnings)


def test_resolve_push_returns_bet():
    bankroll = Bankroll(starting_balance=1000)
    bankroll.place_bet(100)
    bankroll.resolve("push", 100)
    assert bankroll.balance == 1000


def test_resolve_dealer_win_forfeits_bet():
    bankroll = Bankroll(starting_balance=1000)
    bankroll.place_bet(100)
    bankroll.resolve("dealer", 100)
    assert bankroll.balance == 900
