import pytest

from casino.cards import Card
from casino.hand import Hand
from casino.strategies import (
    PlayerStrategy,
    BasicPlayerStrategy,
    AggressivePlayerStrategy,
    DealerStrategy,
    StandardDealerStrategy,
)


def make_hand(*ranks):
    hand = Hand()
    for r in ranks:
        hand.add(Card(r, "hearts"))
    return hand


# ---------------------------------------------------------------------------
# PlayerStrategy (base class)
# ---------------------------------------------------------------------------

def test_player_strategy_name():
    assert PlayerStrategy.name == "base"


def test_player_strategy_should_hit_not_implemented():
    strategy = PlayerStrategy()
    with pytest.raises(NotImplementedError):
        strategy.should_hit(make_hand("10", "5"), Card("6", "spades"))


# ---------------------------------------------------------------------------
# BasicPlayerStrategy
# ---------------------------------------------------------------------------

def test_basic_strategy_name():
    assert BasicPlayerStrategy.name == "basic_17"


def test_basic_strategy_hits_below_17():
    strategy = BasicPlayerStrategy()
    hand = make_hand("10", "6")  # value 16
    assert strategy.should_hit(hand, Card("6", "spades")) is True


def test_basic_strategy_stands_on_17():
    strategy = BasicPlayerStrategy()
    hand = make_hand("10", "7")  # value 17
    assert strategy.should_hit(hand, Card("6", "spades")) is False


def test_basic_strategy_stands_above_17():
    strategy = BasicPlayerStrategy()
    hand = make_hand("10", "9")  # value 19
    assert strategy.should_hit(hand, Card("6", "spades")) is False


# ---------------------------------------------------------------------------
# AggressivePlayerStrategy
# ---------------------------------------------------------------------------

def test_aggressive_strategy_name():
    assert AggressivePlayerStrategy.name == "aggressive_20"


def test_aggressive_strategy_hits_below_20():
    strategy = AggressivePlayerStrategy()
    hand = make_hand("10", "8")  # value 18
    assert strategy.should_hit(hand, Card("6", "spades")) is True


def test_aggressive_strategy_stands_on_20():
    strategy = AggressivePlayerStrategy()
    hand = make_hand("10", "10")  # value 20
    assert strategy.should_hit(hand, Card("6", "spades")) is False


def test_aggressive_strategy_stands_above_20():
    strategy = AggressivePlayerStrategy()
    hand = make_hand("A", "10")  # value 21
    assert strategy.should_hit(hand, Card("6", "spades")) is False


# ---------------------------------------------------------------------------
# DealerStrategy (base class)
# ---------------------------------------------------------------------------

def test_dealer_strategy_name():
    assert DealerStrategy.name == "base"


def test_dealer_strategy_should_hit_not_implemented():
    strategy = DealerStrategy()
    with pytest.raises(NotImplementedError):
        strategy.should_hit(make_hand("10", "5"))


# ---------------------------------------------------------------------------
# StandardDealerStrategy
# ---------------------------------------------------------------------------

def test_standard_dealer_strategy_name():
    assert StandardDealerStrategy.name == "standard_17"


def test_standard_dealer_hits_below_17():
    strategy = StandardDealerStrategy()
    hand = make_hand("10", "6")  # value 16
    assert strategy.should_hit(hand) is True


def test_standard_dealer_stands_on_17():
    strategy = StandardDealerStrategy()
    hand = make_hand("10", "7")  # value 17
    assert strategy.should_hit(hand) is False


def test_standard_dealer_stands_above_17():
    strategy = StandardDealerStrategy()
    hand = make_hand("10", "9")  # value 19
    assert strategy.should_hit(hand) is False
