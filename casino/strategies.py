class PlayerStrategy:
    """Base class for player strategies. Subclasses decide hit/stand."""

    name = "base"

    def should_hit(self, hand, dealer_upcard):
        raise NotImplementedError


class BasicPlayerStrategy(PlayerStrategy):
    """Hits until hand value reaches 17."""

    name = "basic_17"

    def should_hit(self, hand, dealer_upcard):
        return hand.value() < 17


class AggressivePlayerStrategy(PlayerStrategy):
    """Hits until the hand reaches 20 instead of 17. Deliberately
    over-aggressive: kept in the strategy library as a stress-test fixture
    so the anomaly monitor has real, occasional signal to react to."""

    name = "aggressive_20"

    def should_hit(self, hand, dealer_upcard):
        return hand.value() < 20


class DealerStrategy:
    """Base class for dealer strategies."""

    name = "base"

    def should_hit(self, hand):
        raise NotImplementedError


class StandardDealerStrategy(DealerStrategy):
    """Standard casino rule: hit until 17, stand on 17+."""

    name = "standard_17"

    def should_hit(self, hand):
        return hand.value() < 17
