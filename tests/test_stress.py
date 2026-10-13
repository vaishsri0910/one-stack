"""Concurrency stress test. Many threads hammer a few seats with random
hold / hold_many / confirm / release while a fake clock moves forward, then
invariants are asserted. Seed is printed (SEED=<n> to reproduce the *inputs*;
thread interleaving is of course not reproducible)."""

import os
import random
import sys
import threading
import unittest
from collections import defaultdict

from seatholds import (
    EngineError, FakeClock, HoldEngine, HoldStatus, MAX_HOLDS_PER_USER,
)

SEATS = [f"S{i}" for i in range(5)]
USERS = [f"u{i}" for i in range(6)]


def run_stress(seed, threads=8, ops_per_thread=300):
    clock = FakeClock(0.0)
    eng = HoldEngine(clock)
    violations = []           # appended by workers, asserted at the end
    vlock = threading.Lock()
    confirmed_ok = defaultdict(set)   # seat -> hold ids whose confirm returned ok
    created = {}                      # hold id -> (seat, user)
    rec = threading.Lock()
    start = threading.Barrier(threads + 1)

    def violation(msg):
        with vlock:
            violations.append(msg)

    def check_cap(user):
        live = eng.live_holds(user)
        if len(live) > MAX_HOLDS_PER_USER:
            violation(f"{user} has {len(live)} live holds: {live}")

    def worker(tid):
        rng = random.Random(f"{seed}-{tid}")
        mine = []
        start.wait()
        for _ in range(ops_per_thread):
            user = rng.choice(USERS)
            r = rng.random()
            try:
                if r < 0.30:
                    seat = rng.choice(SEATS)
                    hid = eng.hold(seat, user, rng.choice([1, 2, 5, 20]))
                    ids = [(hid, seat)]
                elif r < 0.45:
                    seats = [rng.choice(SEATS) for _ in range(rng.randint(1, 5))]
                    seats_ids = eng.hold_many(user, seats, rng.choice([1, 2, 5, 20]))
                    ids = list(zip(seats_ids, dict.fromkeys(seats)))
                elif r < 0.60 and mine:
                    hid = rng.choice(mine)
                    eng.confirm(hid)
                    with rec:
                        confirmed_ok[created[hid][0]].add(hid)
                    ids = []
                elif r < 0.80 and mine:
                    eng.release(rng.choice(mine))
                    ids = []
                else:
                    clock.advance(rng.choice([0, 0.2, 1, 3]))
                    ids = []
                with rec:
                    for hid, seat in ids:
                        created[hid] = (seat, user)
                for hid, _ in ids:
                    mine.append(hid)
                if len(mine) > 40:
                    del mine[:20]
            except EngineError:
                pass
            except Exception as ex:  # a crash is also a failure
                violation(f"unexpected {type(ex).__name__}: {ex}")
                return
            check_cap(user)

    old = sys.getswitchinterval()
    sys.setswitchinterval(1e-6)  # force aggressive thread switching
    try:
        ts = [threading.Thread(target=worker, args=(i,), daemon=True)
              for i in range(threads)]
        for t in ts:
            t.start()
        start.wait()
        for t in ts:
            t.join(120)
        hung = [t for t in ts if t.is_alive()]
    finally:
        sys.setswitchinterval(old)
    return eng, violations, confirmed_ok, created, hung


class TestStress(unittest.TestCase):
    def test_invariants_under_contention(self):
        # Many short rounds on a fresh engine: sold seats are permanent, so a
        # single long run would just end with every seat sold and nothing left
        # to contend for.
        seed = int(os.environ.get("SEED", random.SystemRandom().randrange(10**9)))
        rounds = int(os.environ.get("ROUNDS", 60))
        print(f"\n[stress] seed={seed} rounds={rounds}")
        tot = defaultdict(int)
        for rnd in range(rounds):
            tag = f"{seed}/round{rnd}"
            eng, violations, confirmed_ok, created, hung = run_stress(f"{seed}-{rnd}")
            self.assertEqual(hung, [], f"threads hung (deadlock?) seed={tag}")
            self.assertEqual(violations, [], f"seed={tag}")
            self.check_invariants(eng, confirmed_ok, tag)
            for h in eng.audit_holds():
                tot[h.status] += 1
        # Make sure the runs actually exercised the interesting paths.
        self.assertGreater(sum(tot.values()), 1000)
        self.assertGreater(tot[HoldStatus.SOLD], 20)
        self.assertGreater(tot[HoldStatus.SUPERSEDED], 20)
        self.assertGreater(tot[HoldStatus.RELEASED], 20)

    def check_invariants(self, eng, confirmed_ok, seed):
        holds = eng.audit_holds()
        by_seat = defaultdict(list)
        for h in holds:
            by_seat[h.seat_id].append(h)

        # Invariant 1: no double sale. Each seat has at most one sold hold, the
        # externally observed successful confirms agree, and seat_status agrees.
        for seat in SEATS:
            sold = [h for h in by_seat[seat] if h.status is HoldStatus.SOLD]
            self.assertLessEqual(len(sold), 1, f"double sale on {seat} seed={seed}")
            self.assertLessEqual(len(confirmed_ok[seat]), 1,
                                 f"two holds confirmed ok on {seat}: "
                                 f"{confirmed_ok[seat]} seed={seed}")
            status = eng.seat_status(seat)
            if sold:
                self.assertEqual(status.state.value, "SOLD")
                self.assertEqual(status.user, sold[0].user_id)
                self.assertEqual(confirmed_ok[seat], {sold[0].id})
            else:
                self.assertNotEqual(status.state.value, "SOLD")
                self.assertEqual(confirmed_ok[seat], set())

        # Invariant 2: nobody ends over the hold limit (also checked live,
        # after every operation, inside the workers).
        for u in USERS:
            self.assertLessEqual(len(eng.live_holds(u)), MAX_HOLDS_PER_USER)

        # Invariant 3: no confirmed hold was retaken: no *other* hold was created
        # on the seat between this hold's creation and its confirmation. This
        # covers both live confirms and late (expired) confirms.
        for seat, hs in by_seat.items():
            for h in hs:
                if h.status is not HoldStatus.SOLD:
                    continue
                for o in hs:
                    if o is not h:
                        self.assertFalse(
                            h.created_seq < o.created_seq < h.closed_seq,
                            f"{h.id} confirmed after {o.id} took {seat} seed={seed}")

        # Invariant 4: on a seat, the live windows [created, min(expiry, closed))
        # of different holds never overlap in clock time (R1).
        for seat, hs in by_seat.items():
            win = []
            for h in hs:
                end = h.expires_at
                if h.closed_at is not None:
                    end = min(end, h.closed_at)
                win.append((h.created_at, end, h.id))
            win.sort()
            for (s1, e1, i1), (s2, e2, i2) in zip(win, win[1:]):
                self.assertLessEqual(
                    e1, s2, f"{i1} and {i2} both live on {seat} seed={seed}")

    def test_hold_many_never_partially_applied_under_contention(self):
        """Two users repeatedly hold_many overlapping sets; at any quiescent
        point a user holds either all of a batch or none of it."""
        eng = HoldEngine(FakeClock())
        stop = threading.Event()
        bad = []

        def go(user, seats):
            for _ in range(2000):
                try:
                    ids = eng.hold_many(user, seats, 1000)
                except EngineError:
                    continue
                live = set(eng.live_holds(user))
                if set(ids) != live:  # all of the batch, nothing else
                    bad.append((user, ids, sorted(live)))
                for i in ids:
                    eng.release(i)

        ts = [threading.Thread(target=go, args=("a", ["S1", "S2", "S3"]), daemon=True),
              threading.Thread(target=go, args=("b", ["S3", "S2", "S1"]), daemon=True),
              threading.Thread(target=go, args=("c", ["S2", "S4", "S1"]), daemon=True)]
        [t.start() for t in ts]
        [t.join(60) for t in ts]
        self.assertFalse(any(t.is_alive() for t in ts), "deadlock")
        self.assertEqual(bad, [])
        # everything released -> nothing may remain held (a partial apply that
        # leaked a hold would show up here)
        for s in ["S1", "S2", "S3", "S4"]:
            self.assertEqual(eng.seat_status(s).state.value, "FREE", s)
        for u in "abc":
            self.assertEqual(eng.live_holds(u), [])


if __name__ == "__main__":
    unittest.main()
