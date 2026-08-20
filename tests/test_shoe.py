from casino.shoe import Shoe
from casino.cards import Card


def test_shoe_init_creates_full_deck():
    shoe = Shoe(num_decks=2, penetration=0.75)
    assert shoe.cards_remaining() == 2 * 52


def test_draw_returns_card_and_reduces_count():
    shoe = Shoe(num_decks=1, penetration=0.75)
    before = shoe.cards_remaining()
    card = shoe.draw()
    assert isinstance(card, Card)
    assert shoe.cards_remaining() == before - 1


def test_needs_reshuffle_false_when_full():
    shoe = Shoe(num_decks=1, penetration=0.75)
    assert shoe.needs_reshuffle() is False


def test_needs_reshuffle_true_past_threshold():
    shoe = Shoe(num_decks=1, penetration=0.75)
    # Manually drain cards below the threshold (25 remaining out of 52)
    while shoe.cards_remaining() > 10:
        shoe._deck.draw()
    assert shoe.needs_reshuffle() is True


def test_draw_auto_reshuffles_when_threshold_reached():
    shoe = Shoe(num_decks=1, penetration=0.75)
    total = shoe.num_decks * 52
    threshold = total * (1 - shoe.penetration)
    # Drain down to exactly at the threshold so the next draw triggers reshuffle
    while shoe.cards_remaining() > threshold:
        shoe._deck.draw()
    assert shoe.needs_reshuffle() is True
    shoe.draw()
    # After reshuffle + one draw, remaining should be total - 1 (fresh deck minus the draw)
    assert shoe.cards_remaining() == total - 1


def test_reshuffle_resets_deck_size():
    shoe = Shoe(num_decks=3, penetration=0.75)
    shoe._deck.draw()
    shoe._deck.draw()
    assert shoe.cards_remaining() == 3 * 52 - 2
    shoe.reshuffle()
    assert shoe.cards_remaining() == 3 * 52


def test_default_parameters():
    shoe = Shoe()
    assert shoe.num_decks == 6
    assert shoe.penetration == 0.75
    assert shoe.cards_remaining() == 6 * 52
