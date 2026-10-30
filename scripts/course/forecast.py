"""Reproducible Monte Carlo using measured weekly completions, including zero weeks."""
import argparse
import csv
from datetime import date, timedelta
import json
from pathlib import Path
import random
from scripts.course.metrics import percentile


def simulate(history, backlog, *, runs=10000, seed=42):
    if not history or any(type(v) is not int or v < 0 for v in history) or not any(history):
        raise ValueError("A nonnegative history with at least one completion is required")
    if type(backlog) is not int or backlog < 0 or runs < 10000:
        raise ValueError("Use a nonnegative backlog and at least 10000 runs")
    rng = random.Random(seed)
    weeks = []
    for _ in range(runs):
        done = count = 0
        while done < backlog:
            done += rng.choice(history)
            count += 1
            if count > 10000:
                raise ValueError("History cannot support a useful forecast")
        weeks.append(count)
    return weeks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--history", type=Path, required=True)
    parser.add_argument("--backlog", type=int, required=True)
    parser.add_argument("--as-of", type=date.fromisoformat, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    with args.history.open() as stream:
        rows = list(csv.DictReader(stream))
    history = [int(r["throughput"]) for r in rows]
    weeks = simulate(history, args.backlog)
    result = {"seed": 42, "runs": 10000, "backlog": args.backlog,
              "history_weeks": len(history), "zero_weeks": history.count(0),
              "as_of": args.as_of.isoformat(), "percentiles": {
                  str(p): {"weeks": percentile(weeks, p / 100),
                           "date": (args.as_of + timedelta(weeks=percentile(weeks, p / 100))).isoformat()}
                  for p in (50, 70, 85, 95)},
              "limitation": "Historical throughput is an input, not a contractual completion promise"}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    for kind in ("hist", "cdf"):
        fig, ax = plt.subplots(figsize=(8, 4.5))
        if kind == "hist":
            ax.hist(weeks, bins=range(min(weeks), max(weeks) + 2), align="left")
            ax.set_ylabel("Simulation count")
        else:
            values = sorted(set(weeks))
            ax.step(values, [sum(w <= value for w in weeks) / len(weeks) for value in values], where="post")
            ax.set_ylabel("Completion probability")
        ax.set_xlabel("Weeks to complete the selected backlog")
        fig.tight_layout()
        fig.savefig(args.output.with_name("forecast-" + kind + ".png"), dpi=160)
        plt.close(fig)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
