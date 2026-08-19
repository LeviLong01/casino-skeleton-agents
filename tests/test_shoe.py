from casino.cards import Card
from casino.shoe import Shoe


def test_shoe_draws_cards():
    shoe = Shoe(num_decks=1)
    card = shoe.draw()
    assert isinstance(card, Card)
    assert shoe.cards_remaining() == 51


def test_shoe_default_num_decks():
    shoe = Shoe()
    assert shoe.num_decks == 6
    assert shoe.cards_remaining() == 6 * 52


def test_shoe_reshuffles_at_penetration():
    shoe = Shoe(num_decks=1, penetration=0.5)
    for _ in range(26):
        shoe.draw()
    assert shoe.cards_remaining() == 26

    # The next draw crosses the 50% penetration threshold, so it should
    # trigger a reshuffle back to a full single-deck shoe (52 cards) before
    # dealing that card.
    shoe.draw()
    assert shoe.cards_remaining() == 51


def test_shoe_needs_reshuffle_reflects_penetration():
    # threshold = 52 * (1 - 0.75) = 13 cards remaining. draw() reshuffles
    # *before* dealing once that threshold is reached, so stop one draw
    # short of it to observe needs_reshuffle() == True without draw()
    # having already corrected it.
    shoe = Shoe(num_decks=1, penetration=0.75)
    assert not shoe.needs_reshuffle()
    for _ in range(39):
        shoe.draw()
    assert shoe.cards_remaining() == 13
    assert shoe.needs_reshuffle()
