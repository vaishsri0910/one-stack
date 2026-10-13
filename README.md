# Seat Hold Engine

Concurrency-safe ticket hold engine (library, in-memory, Python 3.9+, no dependencies).
Assignment: "Nobody Gets the Same Seat Twice".

```python
from seatholds import HoldEngine, FakeClock

clock = FakeClock()
e = HoldEngine(clock)               # default clock: time.monotonic
h = e.hold("A1", "alice", 120)      # -> hold id, or raises an EngineError
e.hold_many("alice", ["A2", "A3"], 120)   # all-or-nothing
e.seat_status("A1")                 # HELD(alice, 1120.0)
e.confirm(h)                        # True
e.seat_status("A1")                 # SOLD(alice)
```

Errors are exceptions with a stable `.code` (see `seatholds/errors.py`).

## Run the tests

```bash
python -m unittest discover -v
```

Reproduce randomized runs: `SEED=<printed seed> python -m unittest tests.test_model tests.test_stress`
(`SEQUENCES=n` and `ROUNDS=n` scale the model/stress tests). The stress test's
*inputs* are reproducible; thread interleaving is not.

## What is here
| File | Purpose |
|------|---------|
| `DECISIONS.md` | Rule conflicts (R3/R4/R5, R2/R6) and every other ambiguity, with choices |
| `seatholds/engine.py` | The engine |
| `tests/test_rules.py` | Example tests pinning each decision, plus concurrency regressions |
| `tests/test_model.py` + `tests/reference.py` | Engine vs. a dumb single-threaded reference on random op sequences (compares results and every seat's status after every op) |
| `tests/test_stress.py` | 8 threads x 60 rounds of random hold/hold_many/confirm/release with a moving fake clock; asserts no double sale, nobody over 4 holds (checked live after every op), no confirmed hold was retaken, no overlapping live holds |
| `BUGS_I_FEAR.md` | A bug class the tests cannot catch, and how to catch it in prod |
| `AI_USAGE.md` | AI disclosure |

## Concurrency design in one paragraph
One lock per seat and one per user. Lock order is always user lock, then seat locks
sorted by seat id, so overlapping `hold_many` calls in opposite order cannot
deadlock; `confirm`/`release`/`seat_status` take only one seat lock. The user lock
makes the "at most 4" check-and-insert atomic. `hold_many` validates every seat
before mutating any, all under all the locks, so it is all-or-nothing. Expiry is
lazy (computed from the injected clock on each call), so no background threads.

## How the conflicting rules were resolved (short version; see DECISIONS.md)
- **R3 vs R4:** a hold's expiry never changes. An expired hold is merely "lapsed":
  the seat shows FREE and anyone may take it, but the lapsed hold can still be
  confirmed until some other hold is created on that seat.
- **R5:** retry of a live hold returns the same id and ignores the new TTL. After
  expiry the same call is a fresh hold (new id).
- **R2 vs R6:** limit is `live holds + new seats in the batch <= 4`; seats the user
  already holds are free; duplicates are de-duplicated.

## What works / what doesn't
Works: all six rules, as specified in DECISIONS.md; tests pass and I mutation-checked
that they fail when locks or semantics are broken.

Not done / limitations: in-memory only (single process); holds are never garbage
collected; late confirm has no time cap; no seat inventory validation; the clock must
be monotonic. Python's GIL makes races harder to provoke, so a green stress test is
evidence, not proof.
