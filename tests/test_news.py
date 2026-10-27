import pandas as pd

from next82 import auto_overrides, news

TODAY = pd.Timestamp("2026-11-01")
PLAYERS = pd.DataFrame([
    {"player_id": 1, "player_name": "Player 1", "status": "Out", "reason": "Left Knee; Surgery",
     "last_game": pd.Timestamp("2026-10-20")},
    {"player_id": 2, "player_name": "Player 2", "status": "Out", "reason": "Right Foot; Fracture",
     "last_game": pd.Timestamp("2026-10-25")},
])


def _row(**kw):
    row = {"player_id": "1", "earliest_return": "2026-12-15", "latest_return": "2027-01-01",
           "note": "Out 6-8 weeks (ESPN, Oct 28)", "source_url": "https://www.espn.com/nba/story/x",
           "date_found": "2026-11-01", "source_date": "2026-10-28", "timeline_type": "return"}
    return {**row, **kw}


def _news(rows):
    df = pd.DataFrame(rows, columns=auto_overrides.NEWS_COLUMNS)
    for c in ("earliest_return", "latest_return", "date_found", "source_date"):
        df[c] = pd.to_datetime(df[c])
    return df


def test_due_every_three_days_or_for_a_new_serious_injury():
    assert news.due({}, TODAY, set())[0]                                              # never run
    state = {"last_run": "2026-10-30", "serious_out": [1]}
    assert not news.due(state, TODAY, {1})[0]                                         # 2 days, nothing new
    assert news.due(state, TODAY, {1, 2})[0]                                          # new serious injury
    assert news.due({"last_run": "2026-10-29", "serious_out": [1]}, TODAY, {1})[0]    # 3 days
    assert news.due(state, TODAY, {1}, force=True)[0]


def test_skips_players_with_a_recent_row_unless_status_changed():
    recent = _news([_row(player_id=1, date_found="2026-10-29"), _row(player_id=2, date_found="2026-10-29")])
    state = {"players": {"1": news.signature("Out", "Left Knee; Surgery"), "2": news.signature("Questionable", "x")}}
    assert list(news.select(PLAYERS, recent, state, TODAY).player_id) == [2]        # 2's status changed
    old = _news([_row(player_id=1, date_found="2026-10-20")])
    assert list(news.select(PLAYERS, old, state, TODAY).player_id) == [1, 2]         # row older than 7 days


def test_validation_accepts_a_clear_dated_row():
    valid, problems = news.validate(pd.DataFrame([_row()]), PLAYERS, TODAY, url_ok=lambda u: True)
    assert problems == [] and valid.earliest_return.iloc[0] == pd.Timestamp("2026-12-15")


def test_validation_rejects_bad_rows():
    bad = [
        _row(player_id="99"),                                     # not a player we searched
        _row(earliest_return="Dec 15"),                           # not a date
        _row(earliest_return="2026-10-10"),                       # before the injury
        _row(source_date="2026-10-01"),                           # source predates the injury
        _row(source_date="2026-11-05"),                           # source in the future
        _row(latest_return="2026-12-01"),                         # latest before earliest
        _row(source_url="espn.com/story"),                        # not a URL
        _row(note=" "),
        _row(timeline_type="maybe"),                              # not a known timeline type
    ]
    valid, problems = news.validate(pd.DataFrame(bad), PLAYERS, TODAY, url_ok=lambda u: True)
    assert valid.empty and len(problems) == len(bad)
    valid, problems = news.validate(pd.DataFrame([_row()]), PLAYERS, TODAY, url_ok=lambda u: False)
    assert valid.empty and "doesn't resolve" in problems[0]
    wrong = pd.DataFrame([_row()]).drop(columns="source_date")
    valid, problems = news.validate(wrong, PLAYERS, TODAY, url_ok=lambda u: True)
    assert valid.empty and "wrong columns" in problems[0]


def test_changed_rows_and_merge_replace_a_players_older_row():
    original = _news([_row(player_id=2, date_found="2026-10-20", source_date="2026-10-26", earliest_return="2026-12-01")])
    edited = pd.concat([original.astype(str).replace({"NaT": ""}), pd.DataFrame([_row(), _row(player_id="2")])])
    edited["latest_return"] = edited.latest_return.replace({"NaT": ""})
    rows = news.changed_rows(original, edited)
    assert len(rows) == 2                                          # the unchanged row isn't re-validated
    valid, _ = news.validate(rows, PLAYERS, TODAY, url_ok=lambda u: True)
    merged, lines = news.merge(original, valid)
    assert sorted(merged.player_id) == [1, 2] and len(merged) == 2
    assert any(line.startswith("News timeline added: player 1") for line in lines)
    assert any(line.startswith("News timeline changed: player 2") for line in lines)


def test_claude_runs_with_only_web_and_the_news_file():
    cmd = news.command("claude", "task")
    assert cmd[:3] == ["claude", "-p", "task"] and "--restricted" in cmd
    assert cmd[cmd.index("--tools") + 1] == "WebSearch,WebFetch,Read,Edit"
    allowed = cmd[cmd.index("--allowedTools") + 1: cmd.index("--permission-mode")]
    assert allowed == ["WebSearch", "WebFetch", "Read(./data/news_timelines.csv)", "Edit(./data/news_timelines.csv)"]
    assert cmd[cmd.index("--permission-mode") + 1] == "dontAsk"
    assert "Bash" not in " ".join(cmd)


def test_prompt_lists_players_and_the_season_end_rule():
    text = news.prompt(PLAYERS.assign(team="A", report_day=TODAY, injury_type=None), TODAY, pd.Timestamp("2027-04-11"))
    assert "1 | Player 1 | A | Out" in text and "earliest_return = 2027-04-12" in text
    assert "Never guess" in text


def test_rejected_sources_are_never_used(monkeypatch):
    url = "https://www.espn.com/nba/story/x"
    monkeypatch.setattr(auto_overrides, "load_rejected", lambda path=None: pd.DataFrame(
        [{"player_id": 1, "source_url": url, "reason": "a check-in date", "date_rejected": "2026-10-27"}]))
    valid, problems = news.validate(pd.DataFrame([_row()]), PLAYERS, TODAY, url_ok=lambda u: True)
    assert valid.empty and "rejected before" in problems[0]
    assert "Never use these sources" in news.prompt(PLAYERS.assign(team="A", report_day=TODAY), TODAY, pd.NaT)


def test_reevaluation_rows_are_accepted_and_kept_as_such():
    valid, problems = news.validate(pd.DataFrame([_row(timeline_type="re-evaluation")]), PLAYERS, TODAY, url_ok=lambda u: True)
    assert problems == [] and valid.timeline_type.iloc[0] == "re-evaluation"


def test_prefers_the_standalone_cli_then_falls_back(tmp_path, monkeypatch):
    standalone = tmp_path / "claude"
    standalone.write_text("#!/bin/sh\n")
    standalone.chmod(0o755)
    monkeypatch.delenv("NEXT82_CLAUDE", raising=False)
    monkeypatch.setattr(news, "STANDALONE_CLAUDE", standalone)
    assert news.claude_binary() == str(standalone)
    monkeypatch.setenv("NEXT82_CLAUDE", "/custom/claude")
    assert news.claude_binary() == "/custom/claude"
    monkeypatch.delenv("NEXT82_CLAUDE")
    monkeypatch.setattr(news, "STANDALONE_CLAUDE", tmp_path / "missing")
    monkeypatch.setattr(news.shutil, "which", lambda name: None)
    monkeypatch.setattr(news.glob, "glob", lambda pattern: ["/x/anthropic.claude-code-2.1.9-darwin-arm64/claude",
                                                             "/x/anthropic.claude-code-2.1.10-darwin-arm64/claude"])
    assert news.claude_binary() == "/x/anthropic.claude-code-2.1.10-darwin-arm64/claude"
