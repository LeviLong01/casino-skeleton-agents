from .cards import Deck


class Shoe:
    """A persistent, multi-round card shoe.

    `Table` currently builds a brand-new `Deck` for every single round,
    which is unrealistic: real blackjack tables deal from a shoe of several
    decks across many hands, reshuffling only once a cut-card penetration
    threshold is reached. `Shoe` is that building block -- draw from it
    across rounds, and it reshuffles itself automatically.
    """

    def __init__(self, num_decks=6, penetration=0.75):
        self.num_decks = num_decks
        self.penetration = penetration
        self._deck = None
        self.reshuffle()

    def reshuffle(self):
        self._deck = Deck(self.num_decks)

    def needs_reshuffle(self):
        total_cards = self.num_decks * 52
        return len(self._deck.cards) <= total_cards * (1 - self.penetration)

    def draw(self):
        if self.needs_reshuffle():
            self.reshuffle()
        return self._deck.draw()

    def cards_remaining(self):
        return len(self._deck.cards)
