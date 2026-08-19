"""Runs the autonomous agent layer unattended.

Every tick this:
  1. simulates a batch of blackjack rounds -- standing in for live casino
     traffic -- and appends them to outcomes.jsonl (occasionally routing a
     batch through the deliberately over-aggressive strategy so the anomaly
     agent has real signal to react to),
  2. lets each of the three agents check its own trigger and act if it's
     warranted.

Nothing here waits for a human. Start it and walk away:

    python3 -m agents.orchestrator
"""
import os
import random
import time

from casino.monitor import Monitor
from casino.strategies import AggressivePlayerStrategy, BasicPlayerStrategy, StandardDealerStrategy
from casino.table import Table

from agents import anomaly_agent, doc_agent, test_writer_agent
from agents.common import log

TICK_SECONDS = int(os.environ.get("AGENT_TICK_SECONDS", "15"))
BATCH_ROUNDS = int(os.environ.get("AGENT_BATCH_ROUNDS", "50"))
FLAWED_STRATEGY_RATE = float(os.environ.get("AGENT_FLAWED_RATE", "0.2"))


def simulate_batch():
    monitor = Monitor()
    player_strategy = (
        AggressivePlayerStrategy() if random.random() < FLAWED_STRATEGY_RATE else BasicPlayerStrategy()
    )
    table = Table(player_strategy, StandardDealerStrategy())
    for _ in range(BATCH_ROUNDS):
        monitor.record(table.play_round())
    log("TrafficGenerator", f"simulated {BATCH_ROUNDS} rounds: {player_strategy.name} vs standard_17")


def main():
    log("Orchestrator", f"starting up. tick={TICK_SECONDS}s batch={BATCH_ROUNDS} rounds/tick.")
    while True:
        try:
            simulate_batch()
            test_writer_agent.tick()
            doc_agent.tick()
            anomaly_agent.tick()
        except Exception as exc:  # keep the layer alive across a single bad tick
            log("Orchestrator", f"tick failed with {exc!r}; continuing.")
        time.sleep(TICK_SECONDS)


if __name__ == "__main__":
    main()
