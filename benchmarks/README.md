# Benchmarks

`omniagi bench` runs offline evaluation suites against real harness behaviour so
that regressions are caught by a number, not a code review. Every evaluator is
deterministic and needs no network or credentials, so a suite scores identically
on every machine and in CI.

```bash
omniagi bench                     # run every suite under benchmarks/
omniagi bench benchmarks/routing.json   # run one suite
omniagi bench --json              # machine-readable report
omniagi bench --verbose           # show passing cases too
```

The exit code is the interface: `0` when every suite meets its `min_accuracy`,
`1` on a regression, `2` when a suite file is malformed.

## Suite format

A suite is a JSON object. `kind` selects the evaluator; `cases[].expect` is
evaluator-specific.

```json
{
  "name": "routing",
  "kind": "routing",
  "min_accuracy": 1.0,
  "cases": [
    {"id": "impl", "task": "implement the parser", "expect": {"specialist": "coder"}}
  ]
}
```

| `kind` | Evaluated against | `expect` keys |
|---|---|---|
| `routing` | `routing.route(task)` | `specialist`, `seat`, `min_confidence`, `max_confidence` |

`min_accuracy` (default `1.0`) is the fraction of cases that must pass for the
suite to be green, so an aspirational suite can track partial progress without
breaking the build.

## Adding a suite

1. Drop a `benchmarks/<name>.json` file using the format above.
2. Run `omniagi bench benchmarks/<name>.json` and confirm it passes.
3. To evaluate a new dimension, register an evaluator in
   `omniagi/bench.py::EVALUATORS`; keep it deterministic and offline.

The committed [`benchmarks/routing.json`](routing.json) pins the specialist,
engine seat and confidence for representative tasks; editing the routing rules
in `registry/harness.json` without updating expectations turns the suite red.
