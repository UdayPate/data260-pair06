"""
The JMeter tooling (jmeter/ and scripts/jmeter_data.py): plans, data files, command lines and the results summary.
The summary tests use a TINY SYNTHETIC .jtl written inside the test, only to check the arithmetic: no real result is invented.
Run from backend/:   python -m pytest tests/test_jmeter_tools.py -q
"""
import csv
import importlib.util
import json
import sys
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.factories import make_company, make_event, make_job, make_student

JMETER = Path(__file__).resolve().parents[2] / "jmeter"


def load(name):
    """Import a script from the jmeter/ folder (it is not a package)."""
    spec = importlib.util.spec_from_file_location(name, JMETER / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


generate_plans, run_load_tests, summarize = load("generate_plans"), load("run_load_tests"), load("summarize")


# ---------------------------------------------------------------- the plans
@pytest.mark.parametrize("name,paths,expect", [
    ("login", ["/auth/login"], ["200"]),
    ("job_search", ["/auth/login", "/jobs"], ["200"]),
    ("apply", ["/auth/login", "/jobs/${job_id}/apply", "/jobs/${job_id}"], ["200", "202"]),
    ("events", ["/auth/login", "/events", "/events/${event_id}/register"], ["200", "201"]),
    ("assistant", ["/auth/login", "/assistant/chat"], ["200"]),
])
def test_each_committed_plan_is_valid_xml_with_the_right_requests(name, paths, expect):
    root = ET.parse(JMETER / "plans" / f"{name}.jmx").getroot()
    assert root.tag == "jmeterTestPlan"
    text = (JMETER / "plans" / f"{name}.jmx").read_text(encoding="utf-8")
    sampler_paths = [e.text for e in root.iter("stringProp") if e.get("name") == "HTTPSampler.path"]
    for path in paths:
        assert path in sampler_paths, path
    for code in expect:
        assert f'name="status is {code}"' in text or f'testname="status is {code}"' in text
    # the users, ramp-up and loops come from -J properties, so one plan serves every concurrency level
    assert "${__P(threads,100)}" in text and "${__P(ramp,30)}" in text and "${__P(loops,1)}" in text


def test_the_committed_plans_match_what_the_generator_writes():
    """Edit generate_plans.py and run it again; never hand-edit a .jmx (this test fails if they drift apart)."""
    for name, xml in generate_plans.build_plans().items():
        assert (JMETER / "plans" / f"{name}.jmx").read_text(encoding="utf-8") == xml, name


def test_setup_and_info_requests_are_labelled_so_the_summary_can_skip_them():
    for name in ("job_search", "apply", "events", "assistant"):
        text = (JMETER / "plans" / f"{name}.jmx").read_text(encoding="utf-8")
        assert 'testname="SETUP login"' in text and 'testname="login"' not in text
    assert 'testname="INFO job page after apply' in (JMETER / "plans" / "apply.jmx").read_text(encoding="utf-8")


def test_the_apply_plan_sends_a_pdf_as_multipart_and_expects_202():
    text = (JMETER / "plans" / "apply.jmx").read_text(encoding="utf-8")
    assert 'name="File.paramname">resume<' in text and "application/pdf" in text
    assert 'name="HTTPSampler.DO_MULTIPART_POST">true<' in text and 'status is 202' in text


# ---------------------------------------------------------------- the runner
def test_the_runner_builds_the_jmeter_command_for_each_level(tmp_path):
    args = SimpleNamespace(host="example.org", port=9060, think=250)
    cmd = run_load_tests.command("jmeter", "assistant", 20, args)
    assert cmd[:4] == ["jmeter", "-n", "-t", str(JMETER / "plans" / "assistant.jmx")]
    for expected in ("-Jthreads=20", "-Jhost=example.org", "-Jport=9060", "-Jresponse_timeout=900000", "-Jthink=250", "-Jloops=1"):
        assert expected in cmd
    assert any(part.endswith("assistant_20.jtl") for part in cmd)
    assert "-Jresponse_timeout=30000" in run_load_tests.command("jmeter", "login", 100, args)
    assert run_load_tests.LEVELS["assistant"] == [5, 10, 20, 50] and run_load_tests.LEVELS["login"] == [100, 200, 300, 400, 500]


def test_every_run_gets_fresh_pairs_and_a_pool_that_is_too_small_stops_the_run(tmp_path):
    header = ["email", "password", "role", "job_id"]
    with (tmp_path / "apply_pool.csv").open("w", newline="") as handle:
        writer = csv.writer(handle, quoting=csv.QUOTE_ALL)
        writer.writerow(header)
        writer.writerows([[f"s{i}@x.test", "pw", "student", i] for i in range(10)])
    assert run_load_tests.take_slice("apply", 4, tmp_path) == 0
    first = list(csv.reader((tmp_path / "apply_pairs.csv").open()))[1:]
    assert run_load_tests.take_slice("apply", 4, tmp_path) == 4
    second = list(csv.reader((tmp_path / "apply_pairs.csv").open()))[1:]
    assert not {tuple(r) for r in first} & {tuple(r) for r in second}          # no pair is used twice
    with pytest.raises(SystemExit):
        run_load_tests.take_slice("apply", 4, tmp_path)                        # only 2 unused pairs are left


def test_dry_run_prints_commands_without_needing_jmeter(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["run_load_tests.py", "--dry-run", "--scenarios", "login", "--levels", "100", "200"])
    monkeypatch.setattr(run_load_tests, "RESULTS", Path(__file__).parent / "_no_such_results_dir_")
    monkeypatch.setattr(Path, "mkdir", lambda *a, **k: None)
    assert run_load_tests.main() == 0
    out = capsys.readouterr().out
    assert out.count("RUN ") == 2 and "-Jthreads=100" in out and "-Jthreads=200" in out


# ---------------------------------------------------------------- the summary
def write_jtl(path, rows):
    """rows = [(label, start_ms, elapsed_ms, success)]"""
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["timeStamp", "elapsed", "label", "responseCode", "success"])
        for label, start, elapsed, ok in rows:
            writer.writerow([start, elapsed, label, 200 if ok else 500, "true" if ok else "false"])


def test_the_summary_computes_average_throughput_error_rate_and_percentiles(tmp_path):
    rows = [("login", 1000 + i * 100, 100 + i, True) for i in range(99)] + [("login", 11000, 1000, False)]    # 100 samples
    rows += [("SETUP login", 0, 9999, True), ("INFO page", 0, 9999, False)]                                    # must be ignored
    write_jtl(tmp_path / "login_100.jtl", rows)
    s = summarize.summarize_file(tmp_path / "login_100.jtl")
    assert s["samples"] == 100 and s["error_pct"] == 1.0 and s["max_ms"] == 1000 and s["min_ms"] == 100
    assert s["avg_ms"] == round((sum(100 + i for i in range(99)) + 1000) / 100, 1)
    assert s["throughput_rps"] == round(100 / ((11000 + 1000 - 1000) / 1000.0), 2)           # samples / (last end - first start)
    assert s["p50_ms"] == 149.5 and s["p95_ms"] < s["p99_ms"] <= 1000


def test_percentile_interpolates_and_handles_edges():
    assert summarize.percentile([], 50) == 0.0 and summarize.percentile([7], 99) == 7
    assert summarize.percentile([10, 20, 30, 40], 50) == 25.0


def test_collect_reads_scenario_and_users_from_the_file_name_and_writes_tables_and_graphs(tmp_path):
    for users, base in ((100, 50), (200, 120)):
        write_jtl(tmp_path / f"login_{users}.jtl", [("login", i * 10, base, True) for i in range(users)])
    write_jtl(tmp_path / f"assistant_5.jtl", [("assistant chat", i * 1000, 20000 + i * 100, True) for i in range(5)])
    (tmp_path / "notes.txt").write_text("not a result")
    found = summarize.collect(tmp_path)
    assert sorted(found) == ["assistant", "login"] and sorted(found["login"]) == [100, 200]
    out = tmp_path / "out"
    text = summarize.write_outputs(found, out)
    assert "| 100 |" in text and "| 200 |" in text and "p99 ms" in text
    graph = (out / "avg_response_vs_concurrency.svg").read_text()
    assert graph.startswith("<svg") and "Average response time vs concurrent users" in graph and "<polyline" in graph
    assert (out / "assistant_latency.svg").exists() and json.loads((out / "results.json").read_text())["login"]["100"]["samples"] == 100
    ET.fromstring(graph)                                                                      # the SVG is well-formed XML


# ---------------------------------------------------------------- the data files
def test_the_data_script_writes_only_pairs_that_can_still_be_used(db, tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("jmeter_data", Path(__file__).resolve().parents[1] / "scripts" / "jmeter_data.py")
    data = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(data)
    monkeypatch.setattr(data, "DATA_DIR", tmp_path)
    company = make_company(db, name="Acme", email="a@acme.test")
    today = date.today()
    jobs = [make_job(db, company.id, title=f"J{i}", description="d", category="internship", city="San Jose", state="CA", is_remote=False,
                     pay_period="hourly", salary_min=20, salary_max=30, posting_date=today - timedelta(days=2),
                     deadline=today + timedelta(days=(30 if i < 2 else -5))) for i in range(3)]      # the third job is closed
    cs = make_student(db, email="cs@s.test", major="Computer Science")
    mk = make_student(db, email="mk@s.test", major="Marketing")
    open_event = make_event(db, company.id, name="CS Fair", description="d", city="San Jose", location="Hall",
                            event_datetime=datetime.combine(today + timedelta(days=9), datetime.min.time()), eligible_majors=["Computer Science"])
    make_event(db, company.id, name="Past", description="d", city="San Jose", location="Hall",
               event_datetime=datetime.combine(today - timedelta(days=9), datetime.min.time()), eligible_majors=["All"])
    from tests.factories import make_application
    make_application(db, cs.id, jobs[0].id)                                                   # this pair is already used
    assert data.main() == 0
    rows = lambda name: list(csv.DictReader((tmp_path / name).open(encoding="utf-8")))
    assert {r["email"] for r in rows("students.csv")} == {"cs@s.test", "mk@s.test"} and rows("students.csv")[0]["password"] == "Password123!"
    pairs = {(r["email"], int(r["job_id"])) for r in rows("apply_pool.csv")}
    assert pairs == {("cs@s.test", jobs[1].id), ("mk@s.test", jobs[0].id), ("mk@s.test", jobs[1].id)}     # open jobs, not yet applied
    assert [(r["email"], int(r["event_id"])) for r in rows("event_pool.csv")] == [("cs@s.test", open_event.id)]   # eligible and upcoming only
    assert len(rows("assistant_messages.csv")) == 50 and (tmp_path / "resume.pdf").read_bytes().startswith(b"%PDF")
