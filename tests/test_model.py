"""Randomized model-based test: engine vs. the dumb reference on random op
sequences. Seed is printed; reproduce with  SEED=<n> python -m unittest ..."""

import os
import random
import unittest

from seatholds import EngineError, FakeClock, HoldEngine
from tests.reference import RefEngine

SEATS = ["A", "B", "C", "D", "E", "F"]
USERS = ["u1", "u2", "u3"]


def call(fn, *args):
    try:
        return ("ok", fn(*args))
    except EngineError as ex:
        return ("err", ex.code)


def status_tuple(s):
    return (s.state.value, s.user, s.expires_at)


def run_sequence(seed, steps=400):
    rng = random.Random(seed)
    clock = FakeClock(0.0)
    eng = HoldEngine(clock)
    ref = RefEngine(clock)
    known = []
    log = []
    for step in range(steps):
        op = rng.choices(
            ["hold", "hold_many", "confirm", "release", "advance"],
            [30, 20, 20, 12, 18])[0]
        if op == "hold":
            a = (rng.choice(SEATS), rng.choice(USERS), rng.choice([1, 3, 10]))
            r1, r2 = call(eng.hold, *a), ref.hold(*a)
        elif op == "hold_many":
            seats = [rng.choice(SEATS) for _ in range(rng.randint(0, 6))]
            a = (rng.choice(USERS), seats, rng.choice([1, 3, 10]))
            r1, r2 = call(eng.hold_many, *a), ref.hold_many(*a)
        elif op in ("confirm", "release"):
            hid = (rng.choice(known) if known and rng.random() < 0.9
                   else "bogus")
            a = (hid,)
            r1 = call(getattr(eng, op), *a)
            r2 = getattr(ref, op)(*a)
        else:
            dt = rng.choice([0, 0.5, 1, 2, 5])
            clock.advance(dt)
            a = (dt,)
            r1 = r2 = ("ok", None)
        log.append((step, op, a, r1, r2))
        if r1 != r2:
            raise AssertionError(
                f"seed={seed} step={step} {op}{a}: engine={r1} ref={r2}")
        if op in ("hold", "hold_many") and r1[0] == "ok":
            known.extend(r1[1] if op == "hold_many" else [r1[1]])
        for s in SEATS:
            e, r = status_tuple(eng.seat_status(s)), ref.seat_status(s)
            if e != r:
                raise AssertionError(
                    f"seed={seed} step={step} after {op}{a}: "
                    f"seat {s} engine={e} ref={r}")
    return log


class TestModel(unittest.TestCase):
    def test_engine_matches_reference(self):
        base = int(os.environ.get("SEED", random.SystemRandom().randrange(10**9)))
        n = int(os.environ.get("SEQUENCES", 300))
        print(f"\n[model] base seed={base} sequences={n}")
        for i in range(n):
            run_sequence(base + i)

    def test_sequences_exercise_the_interesting_paths(self):
        """Guard against a vacuous model test: the generator must actually
        reach late confirms, lost holds, limit errors and retries."""
        seen = set()
        for seed in range(100):
            for _, op, _, r1, _ in run_sequence(seed):
                seen.add((op, r1[0] if r1[0] == "err" else "ok",
                          r1[1] if r1[0] == "err" else None))
        for needed in [("confirm", "err", "HOLD_LOST"),
                       ("hold", "err", "HOLD_LIMIT_EXCEEDED"),
                       ("hold", "err", "SEAT_HELD"),
                       ("hold", "err", "SEAT_SOLD"),
                       ("hold_many", "err", "HOLD_LIMIT_EXCEEDED"),
                       ("hold_many", "err", "SEAT_HELD"),
                       ("confirm", "err", "HOLD_RELEASED"),
                       ("release", "err", "ALREADY_SOLD")]:
            self.assertIn(needed, seen)


if __name__ == "__main__":
    unittest.main()
