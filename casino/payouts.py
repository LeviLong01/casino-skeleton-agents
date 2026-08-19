class Bankroll:
    """Tracks a player's chip balance and resolves bets against a round's
    outcome.

    `Table`/`strategies` only ever reason about who won a hand in the
    abstract ("player", "dealer", or "push"); nothing in the simulator
    currently models money. `Bankroll` is the payout layer that turns a win
    into an actual amount, including the standard 3:2 blackjack bonus. It's
    intentionally decoupled from `Table` -- it takes the outcome string and
    a caller-supplied blackjack flag (e.g. from `Hand.is_blackjack()`)
    rather than a `Table` instance, so it can be dropped in without changing
    the round-playing code at all.
    """

    BLACKJACK_PAYOUT = 1.5
    STANDARD_PAYOUT = 1.0

    def __init__(self, starting_balance=1000):
        self.balance = starting_balance

    def place_bet(self, amount):
        if amount > self.balance:
            raise ValueError("bet exceeds available balance")
        self.balance -= amount
        return amount

    def resolve(self, winner, bet, player_blackjack=False):
        """`winner` is the 'winner' field from a Table.play_round() outcome:
        'player', 'dealer', or 'push'. Returns the new balance."""
        if winner == "push":
            self.balance += bet
        elif winner == "player":
            multiplier = self.BLACKJACK_PAYOUT if player_blackjack else self.STANDARD_PAYOUT
            self.balance += bet + bet * multiplier
        # winner == "dealer": the bet was already deducted in place_bet.
        return self.balance
