import casino.simulate as simulate


class FakeMonitor:
    """Stand-in for Monitor that records in-memory instead of touching disk."""

    instances = []

    def __init__(self, *args, **kwargs):
        self.recorded = []
        FakeMonitor.instances.append(self)

    def record(self, outcome):
        self.recorded.append(outcome)


class FakeTable:
    """Stand-in for Table that returns canned outcomes without randomness."""

    instances = []

    def __init__(self, player_strategy, dealer_strategy, *args, **kwargs):
        self.player_strategy = player_strategy
        self.dealer_strategy = dealer_strategy
        self.play_round_calls = 0
        FakeTable.instances.append(self)

    def play_round(self):
        self.play_round_calls += 1
        return {"winner": "player", "round": self.play_round_calls}


def setup_function(_function):
    # Ensure each test starts with a clean slate of tracked instances.
    FakeMonitor.instances.clear()
    FakeTable.instances.clear()


def test_run_uses_default_num_rounds(monkeypatch):
    monkeypatch.setattr(simulate, "Table", FakeTable)
    monkeypatch.setattr(simulate, "Monitor", FakeMonitor)

    simulate.run()

    table = FakeTable.instances[0]
    monitor = FakeMonitor.instances[0]
    assert table.play_round_calls == 100
    assert len(monitor.recorded) == 100


def test_run_uses_custom_num_rounds(monkeypatch):
    monkeypatch.setattr(simulate, "Table", FakeTable)
    monkeypatch.setattr(simulate, "Monitor", FakeMonitor)

    simulate.run(num_rounds=5)

    table = FakeTable.instances[0]
    monitor = FakeMonitor.instances[0]
    assert table.play_round_calls == 5
    assert len(monitor.recorded) == 5


def test_run_zero_rounds_does_nothing(monkeypatch):
    monkeypatch.setattr(simulate, "Table", FakeTable)
    monkeypatch.setattr(simulate, "Monitor", FakeMonitor)

    simulate.run(num_rounds=0)

    table = FakeTable.instances[0]
    monitor = FakeMonitor.instances[0]
    assert table.play_round_calls == 0
    assert monitor.recorded == []


def test_run_records_outcomes_from_play_round(monkeypatch):
    monkeypatch.setattr(simulate, "Table", FakeTable)
    monkeypatch.setattr(simulate, "Monitor", FakeMonitor)

    simulate.run(num_rounds=3)

    monitor = FakeMonitor.instances[0]
    assert monitor.recorded == [
        {"winner": "player", "round": 1},
        {"winner": "player", "round": 2},
        {"winner": "player", "round": 3},
    ]


def test_run_prints_summary_message(monkeypatch, capsys):
    monkeypatch.setattr(simulate, "Table", FakeTable)
    monkeypatch.setattr(simulate, "Monitor", FakeMonitor)

    simulate.run(num_rounds=7)

    captured = capsys.readouterr()
    assert "Simulated 7 rounds" in captured.out
    assert "outcomes.jsonl" in captured.out


def test_run_prints_default_summary_message(monkeypatch, capsys):
    monkeypatch.setattr(simulate, "Table", FakeTable)
    monkeypatch.setattr(simulate, "Monitor", FakeMonitor)

    simulate.run()

    captured = capsys.readouterr()
    assert "Simulated 100 rounds" in captured.out


def test_run_constructs_table_with_expected_strategies(monkeypatch):
    monkeypatch.setattr(simulate, "Table", FakeTable)
    monkeypatch.setattr(simulate, "Monitor", FakeMonitor)

    simulate.run(num_rounds=1)

    table = FakeTable.instances[0]
    assert table.player_strategy.name == "basic_17"
    assert table.dealer_strategy.name == "standard_17"


def test_run_end_to_end_with_real_table(monkeypatch, tmp_path):
    # Integration-style test using the real Table/strategies but redirecting
    # Monitor's output to a temp file so we never touch the repo's outcomes.jsonl.
    real_monitor_cls = simulate.Monitor

    def fake_monitor_factory():
        return real_monitor_cls(path=str(tmp_path / "outcomes.jsonl"))

    monkeypatch.setattr(simulate, "Monitor", fake_monitor_factory)

    simulate.run(num_rounds=4)

    outcomes_file = tmp_path / "outcomes.jsonl"
    lines = outcomes_file.read_text().splitlines()
    assert len(lines) == 4
