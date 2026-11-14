"""
Runs the JMeter load tests, one run per scenario and concurrency level (Lab 2, Part 5).

    python jmeter/run_load_tests.py                              (all five scenarios, all levels)
    python jmeter/run_load_tests.py --scenarios login job_search --levels 100 200
    python jmeter/run_load_tests.py --dry-run                    (only print the JMeter commands)

Needs: Apache JMeter 5.x (set JMETER_HOME to its folder, or put jmeter on the PATH), the stack running (see README), the
database seeded, and the test data written by  python -m scripts.jmeter_data  (from backend/).

For every run it
  1. writes the data files the plan reads (for apply and events: a FRESH slice of the unused-pairs pool, because each
     (student, job) and (student, event) pair can be used only once; the position in the pool is remembered in
     jmeter/data/pool_offsets.json so the next run takes the next pairs),
  2. starts JMeter without its window (-n) with the right properties (-J), writing docs/lab2/jmeter/results/<scenario>_<users>.jtl,
  3. waits a few seconds so the system can settle before the next level.
Afterwards:  python jmeter/summarize.py   makes the tables and the graphs.

Levels: 100, 200, 300, 400, 500 users for login, job_search, apply and events; 5, 10, 20, 50 for the assistant.
"""
import argparse
import csv
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLANS = ROOT / "jmeter" / "plans"
DATA = ROOT / "jmeter" / "data"
RESULTS = ROOT / "docs" / "lab2" / "jmeter" / "results"
LEVELS = {"login": [100, 200, 300, 400, 500], "job_search": [100, 200, 300, 400, 500], "apply": [100, 200, 300, 400, 500],
          "events": [100, 200, 300, 400, 500], "assistant": [5, 10, 20, 50]}
LOOPS = {"login": 1, "job_search": 3, "apply": 1, "events": 1, "assistant": 1}      # requests per user
POOLS = {"apply": ("apply_pool.csv", "apply_pairs.csv"), "events": ("event_pool.csv", "event_pairs.csv")}


def find_jmeter(explicit=None):
    """The JMeter launcher: --jmeter-home, then JMETER_HOME, then the PATH."""
    home = explicit or os.environ.get("JMETER_HOME")
    name = "jmeter.bat" if os.name == "nt" else "jmeter"
    if home and (Path(home) / "bin" / name).exists():
        return str(Path(home) / "bin" / name)
    return shutil.which(name) or shutil.which("jmeter")


def take_slice(scenario: str, users: int, data_dir: Path = DATA) -> int:
    """Write the next `users` never-used pairs of the pool to the plan's data file. Returns the position it started at."""
    pool_name, target_name = POOLS[scenario]
    offsets_file = data_dir / "pool_offsets.json"
    offsets = json.loads(offsets_file.read_text()) if offsets_file.exists() else {}
    start = offsets.get(scenario, 0)
    with (data_dir / pool_name).open(newline="", encoding="utf-8") as handle:
        rows = list(csv.reader(handle))
    header, body = rows[0], rows[1:]
    chosen = body[start:start + users]
    if len(chosen) < users:
        raise SystemExit(f"The {scenario} pool has only {len(chosen)} unused pairs left for {users} users. "
                         "Write a bigger pool (python -m scripts.jmeter_data) or reseed the database.")
    with (data_dir / target_name).open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, quoting=csv.QUOTE_ALL)
        writer.writerow(header)
        writer.writerows(chosen)
    offsets[scenario] = start + users
    offsets_file.write_text(json.dumps(offsets))
    return start


def command(jmeter: str, scenario: str, users: int, args) -> list:
    """The JMeter command line for one run."""
    ramp = max(5, min(60, users // 10))                          # start the users over a few seconds, not all at once
    timeout = 900000 if scenario == "assistant" else 30000       # a model on a CPU can take minutes to answer
    out = RESULTS / f"{scenario}_{users}.jtl"
    return [jmeter, "-n", "-t", str(PLANS / f"{scenario}.jmx"), "-l", str(out), "-j", str(RESULTS / f"{scenario}_{users}.log"),
            f"-Jthreads={users}", f"-Jramp={ramp}", f"-Jloops={LOOPS[scenario]}", f"-Jhost={args.host}", f"-Jport={args.port}",
            f"-Jdata={DATA.as_posix()}", f"-Jresponse_timeout={timeout}", f"-Jthink={args.think}"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenarios", nargs="+", default=list(LEVELS), choices=list(LEVELS))
    parser.add_argument("--levels", nargs="+", type=int, help="override the concurrency levels")
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=9060)
    parser.add_argument("--think", type=int, default=500, help="milliseconds between a user's requests")
    parser.add_argument("--settle", type=int, default=15, help="seconds to wait between runs")
    parser.add_argument("--jmeter-home")
    parser.add_argument("--force", action="store_true", help="run again even if the result file exists")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    jmeter = find_jmeter(args.jmeter_home)
    if not jmeter and not args.dry_run:
        print("JMeter was not found. Install Apache JMeter 5.x and set JMETER_HOME (or add it to the PATH).")
        return 2
    RESULTS.mkdir(parents=True, exist_ok=True)
    for scenario in args.scenarios:
        for users in args.levels or LEVELS[scenario]:
            target = RESULTS / f"{scenario}_{users}.jtl"
            if target.exists() and not args.force:
                print(f"skip {target.name} (exists; use --force to run again)")
                continue
            if scenario in POOLS and not args.dry_run:
                print(f"{scenario}: using pairs from position {take_slice(scenario, users)}")
            cmd = command(jmeter or "jmeter", scenario, users, args)
            print("RUN", " ".join(cmd))
            if args.dry_run:
                continue
            began = time.time()
            if subprocess.run(cmd).returncode != 0:
                print(f"JMeter failed for {scenario} at {users} users")
                return 1
            print(f"  done in {time.time() - began:.0f} s")
            time.sleep(args.settle)
    return 0


if __name__ == "__main__":
    sys.exit(main())
