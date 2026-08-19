from casino.cards import Card, Deck, SUITS, RANKS


def test_deck_default_size():
    deck = Deck()
    assert len(deck.cards) == len(SUITS) * len(RANKS)


def test_deck_multiple_decks_size():
    num_decks = 3
    deck = Deck(num_decks=num_decks)
    assert len(deck.cards) == len(SUITS) * len(RANKS) * num_decks


def test_deck_contains_only_valid_cards():
    deck = Deck()
    for card in deck.cards:
        assert isinstance(card, Card)
        assert card.rank in RANKS
        assert card.suit in SUITS


def test_deck_has_no_duplicate_card_objects_for_single_deck():
    deck = Deck(num_decks=1)
    # single deck should have exactly one of each rank/suit combo
    combos = [(c.rank, c.suit) for c in deck.cards]
    assert sorted(combos) == sorted((r, s) for s in SUITS for r in RANKS)


def test_deck_draw_reduces_size():
    deck = Deck()
    initial_size = len(deck.cards)
    card = deck.draw()
    assert isinstance(card, Card)
    assert len(deck.cards) == initial_size - 1


def test_deck_draw_all_cards_empties_deck():
    deck = Deck()
    total = len(deck.cards)
    drawn = [deck.draw() for _ in range(total)]
    assert len(deck.cards) == 0
    assert len(drawn) == total
    # all drawn cards should be unique instances covering full combo set
    combos = sorted((c.rank, c.suit) for c in drawn)
    assert combos == sorted((r, s) for s in SUITS for r in RANKS)


def test_deck_draw_from_empty_raises():
    deck = Deck()
    deck.cards = []
    import pytest
    with pytest.raises(IndexError):
        deck.draw()
