import json

from casino.monitor import Monitor


def test_record_writes_json_line(tmp_path):
    path = tmp_path / "outcomes.jsonl"
    monitor = Monitor(path=str(path))

    monitor.record({"result": "win", "amount": 10})

    lines = path.read_text().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0]) == {"result": "win", "amount": 10}


def test_record_appends_multiple_outcomes(tmp_path):
    path = tmp_path / "outcomes.jsonl"
    monitor = Monitor(path=str(path))

    monitor.record({"result": "win"})
    monitor.record({"result": "loss"})
    monitor.record({"result": "push"})

    lines = path.read_text().splitlines()
    assert len(lines) == 3
    assert [json.loads(line)["result"] for line in lines] == ["win", "loss", "push"]


def test_record_creates_file_if_missing(tmp_path):
    path = tmp_path / "new_dir_outcomes.jsonl"
    assert not path.exists()

    monitor = Monitor(path=str(path))
    monitor.record({"result": "blackjack"})

    assert path.exists()
    assert json.loads(path.read_text().splitlines()[0]) == {"result": "blackjack"}


def test_default_path_uses_outcomes_jsonl():
    monitor = Monitor()
    assert monitor.path.endswith("outcomes.jsonl")


def test_record_with_nested_data(tmp_path):
    path = tmp_path / "outcomes.jsonl"
    monitor = Monitor(path=str(path))

    outcome = {"result": "win", "hand": ["10H", "7C"], "meta": {"dealer": "bust"}}
    monitor.record(outcome)

    recorded = json.loads(path.read_text().splitlines()[0])
    assert recorded == outcome
