"""Example-based tests that pin each decision in DECISIONS.md."""

import threading
import unittest

from seatholds import (
    AlreadySold, FakeClock, HoldEngine, HoldLimitExceeded, HoldLost,
    HoldNotFound, HoldReleased, InvalidArgument, SeatHeld, SeatSold, State,
)


class Base(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.e = HoldEngine(self.clock)


class TestR1(Base):
    def test_other_user_cannot_hold_held_seat(self):
        self.e.hold("A1", "u1", 10)
        with self.assertRaises(SeatHeld):
            self.e.hold("A1", "u2", 10)

    def test_cannot_hold_sold_seat_even_same_user(self):
        h = self.e.hold("A1", "u1", 10)
        self.e.confirm(h)
        for u in ("u1", "u2"):
            with self.assertRaises(SeatSold):
                self.e.hold("A1", u, 10)
        self.assertEqual(self.e.seat_status("A1").state, State.SOLD)

    def test_seat_free_after_expiry_for_others(self):
        self.e.hold("A1", "u1", 10)
        self.clock.advance(10)  # boundary: expired (D7)
        self.assertEqual(self.e.seat_status("A1").state, State.FREE)
        self.e.hold("A1", "u2", 10)


class TestR2(Base):
    def test_fifth_hold_rejected(self):
        for i in range(4):
            self.e.hold(f"S{i}", "u1", 100)
        with self.assertRaises(HoldLimitExceeded):
            self.e.hold("S4", "u1", 100)

    def test_expired_holds_free_quota(self):
        for i in range(4):
            self.e.hold(f"S{i}", "u1", 5)
        self.clock.advance(5)
        self.e.hold("S9", "u1", 5)

    def test_release_frees_quota(self):
        ids = [self.e.hold(f"S{i}", "u1", 100) for i in range(4)]
        self.e.release(ids[0])
        self.e.hold("S9", "u1", 100)

    def test_confirmed_seats_do_not_count(self):  # D6
        for i in range(4):
            self.e.confirm(self.e.hold(f"S{i}", "u1", 100))
        for i in range(4, 8):
            self.e.hold(f"S{i}", "u1", 100)

    def test_concurrent_holds_by_same_user_never_exceed_limit(self):
        import sys
        old = sys.getswitchinterval()
        sys.setswitchinterval(1e-6)
        try:
            for _ in range(300):
                e = HoldEngine(FakeClock())
                ok, lock = [], threading.Lock()
                gate = threading.Barrier(12)

                def go(i):
                    gate.wait()
                    try:
                        if i % 2:
                            got = [e.hold(f"S{i}", "u1", 100)]
                        else:
                            got = e.hold_many("u1", [f"S{i}", f"T{i}"], 100)
                        with lock:
                            ok.extend(got)
                    except HoldLimitExceeded:
                        pass
                ts = [threading.Thread(target=go, args=(i,), daemon=True)
                      for i in range(12)]
                [t.start() for t in ts]
                [t.join() for t in ts]
                self.assertLessEqual(len(e.live_holds("u1")), 4)
                self.assertLessEqual(len(ok), 4 + 4)  # hold_many may add 2 each
        finally:
            sys.setswitchinterval(old)


class TestR3R4(Base):
    def test_confirm_before_expiry(self):
        h = self.e.hold("A1", "u1", 10)
        self.clock.advance(9.9)
        self.assertTrue(self.e.confirm(h))

    def test_late_confirm_allowed_if_untouched(self):
        h = self.e.hold("A1", "u1", 10)
        self.clock.advance(1000)
        self.assertEqual(self.e.seat_status("A1").state, State.FREE)
        self.assertTrue(self.e.confirm(h))
        s = self.e.seat_status("A1")
        self.assertEqual((s.state, s.user), (State.SOLD, "u1"))

    def test_late_confirm_rejected_if_retaken(self):
        h1 = self.e.hold("A1", "u1", 10)
        self.clock.advance(11)
        self.e.hold("A1", "u2", 10)
        with self.assertRaises(HoldLost):
            self.e.confirm(h1)

    def test_retaken_then_released_still_lost(self):
        h1 = self.e.hold("A1", "u1", 10)
        self.clock.advance(11)
        h2 = self.e.hold("A1", "u2", 10)
        self.e.release(h2)
        with self.assertRaises(HoldLost):
            self.e.confirm(h1)

    def test_retaken_then_expired_still_lost(self):
        h1 = self.e.hold("A1", "u1", 10)
        self.clock.advance(11)
        self.e.hold("A1", "u2", 10)
        self.clock.advance(100)
        with self.assertRaises(HoldLost):
            self.e.confirm(h1)

    def test_late_confirm_does_not_need_free_quota(self):
        h = self.e.hold("A1", "u1", 5)
        self.clock.advance(6)
        for i in range(4):
            self.e.hold(f"S{i}", "u1", 100)
        self.assertTrue(self.e.confirm(h))

    def test_late_confirm_blocks_later_holders(self):
        h = self.e.hold("A1", "u1", 5)
        self.clock.advance(6)
        self.e.confirm(h)
        with self.assertRaises(SeatSold):
            self.e.hold("A1", "u2", 5)

    def test_expires_at_never_changes(self):
        h = self.e.hold("A1", "u1", 10)
        exp = self.e.seat_status("A1").expires_at
        self.clock.advance(3)
        self.e.hold("A1", "u1", 1000)           # retry with bigger ttl
        self.assertEqual(self.e.seat_status("A1").expires_at, exp)
        self.clock.advance(7)                   # now == exp -> expired
        self.assertEqual(self.e.seat_status("A1").state, State.FREE)
        hold = {x.id: x for x in self.e.audit_holds()}[h]
        self.assertEqual(hold.expires_at, exp)  # also after a late confirm
        self.e.confirm(h)
        self.assertEqual(hold.expires_at, exp)


class TestR5(Base):
    def test_retry_returns_same_hold_ignores_ttl(self):
        h1 = self.e.hold("A1", "u1", 10)
        exp = self.e.seat_status("A1").expires_at
        self.clock.advance(4)
        h2 = self.e.hold("A1", "u1", 50)
        self.assertEqual(h1, h2)
        self.assertEqual(self.e.seat_status("A1").expires_at, exp)

    def test_retry_does_not_consume_quota(self):
        for _ in range(10):
            self.e.hold("S0", "u1", 100)
        for i in range(1, 4):
            self.e.hold(f"S{i}", "u1", 100)

    def test_retry_at_limit_succeeds(self):  # D4
        ids = [self.e.hold(f"S{i}", "u1", 100) for i in range(4)]
        self.assertEqual(self.e.hold("S2", "u1", 100), ids[2])

    def test_retry_after_expiry_is_new_hold(self):  # D3
        h1 = self.e.hold("A1", "u1", 10)
        self.clock.advance(11)
        h2 = self.e.hold("A1", "u1", 10)
        self.assertNotEqual(h1, h2)
        with self.assertRaises(HoldLost):
            self.e.confirm(h1)
        self.assertTrue(self.e.confirm(h2))

    def test_retry_after_expiry_loses_to_other_user(self):
        self.e.hold("A1", "u1", 10)
        self.clock.advance(11)
        self.e.hold("A1", "u2", 10)
        with self.assertRaises(SeatHeld):
            self.e.hold("A1", "u1", 10)


class TestR6(Base):
    def test_all_or_nothing_on_unavailable_seat(self):
        self.e.hold("B", "u2", 100)
        with self.assertRaises(SeatHeld):
            self.e.hold_many("u1", ["A", "B", "C"], 100)
        self.assertEqual(self.e.live_holds("u1"), [])
        self.assertEqual(self.e.seat_status("A").state, State.FREE)
        self.assertEqual(self.e.seat_status("C").state, State.FREE)

    def test_all_or_nothing_on_limit(self):
        self.e.hold("X", "u1", 100)
        self.e.hold("Y", "u1", 100)
        with self.assertRaises(HoldLimitExceeded):
            self.e.hold_many("u1", ["A", "B", "C"], 100)
        self.assertEqual(len(self.e.live_holds("u1")), 2)
        self.assertEqual(self.e.seat_status("A").state, State.FREE)

    def test_five_new_seats_always_fail(self):  # D5
        with self.assertRaises(HoldLimitExceeded):
            self.e.hold_many("u1", list("ABCDE"), 100)

    def test_four_seats_ok(self):
        ids = self.e.hold_many("u1", list("ABCD"), 100)
        self.assertEqual(len(set(ids)), 4)

    def test_already_held_seats_cost_nothing(self):  # D5
        first = self.e.hold_many("u1", list("ABC"), 100)
        again = self.e.hold_many("u1", list("ABCD"), 100)
        self.assertEqual(again[:3], first)
        self.assertEqual(len(self.e.live_holds("u1")), 4)

    def test_duplicates_deduped(self):
        ids = self.e.hold_many("u1", ["A", "A", "B", "A"], 100)
        self.assertEqual(len(ids), 2)
        self.assertEqual(len(self.e.live_holds("u1")), 2)

    def test_five_requested_but_dupes_make_it_four(self):
        self.assertEqual(
            len(self.e.hold_many("u1", list("ABCDA"), 100)), 4)

    def test_empty(self):
        self.assertEqual(self.e.hold_many("u1", [], 100), [])

    def test_unavailable_error_wins_over_limit(self):
        self.e.hold("Z", "u2", 100)
        with self.assertRaises(SeatHeld):
            self.e.hold_many("u1", ["Z", "A", "B", "C", "D"], 100)

    def test_opposite_order_no_deadlock(self):
        seats = [f"S{i}" for i in range(4)]
        stop = threading.Event()
        errors = []

        def worker(user, order):
            from seatholds import EngineError
            n = 0
            while not stop.is_set() and n < 3000:
                n += 1
                try:
                    ids = self.e.hold_many(user, order, 1000)
                    for i in ids:
                        self.e.release(i)
                except EngineError:
                    pass
                except Exception as ex:  # pragma: no cover
                    errors.append(ex)
                    return

        t1 = threading.Thread(target=worker, args=("u1", seats), daemon=True)
        t2 = threading.Thread(target=worker,
                              args=("u2", list(reversed(seats))), daemon=True)
        t1.start(); t2.start()
        t1.join(30); t2.join(30)
        stop.set()
        self.assertFalse(t1.is_alive() or t2.is_alive(), "deadlock")
        self.assertEqual(errors, [])


class TestMisc(Base):
    def test_confirm_release_idempotent(self):
        h = self.e.hold("A", "u1", 10)
        self.assertTrue(self.e.confirm(h))
        self.assertTrue(self.e.confirm(h))
        h2 = self.e.hold("B", "u1", 10)
        self.e.release(h2)
        self.assertTrue(self.e.release(h2))

    def test_errors(self):
        h = self.e.hold("A", "u1", 10)
        self.e.confirm(h)
        with self.assertRaises(AlreadySold):
            self.e.release(h)
        h2 = self.e.hold("B", "u1", 10)
        self.e.release(h2)
        with self.assertRaises(HoldReleased):
            self.e.confirm(h2)
        with self.assertRaises(HoldNotFound):
            self.e.confirm("nope")
        with self.assertRaises(HoldNotFound):
            self.e.release(None)

    def test_release_lapsed_gives_up_late_confirm(self):  # D13
        h = self.e.hold("A", "u1", 5)
        self.clock.advance(6)
        self.assertTrue(self.e.release(h))
        with self.assertRaises(HoldReleased):
            self.e.confirm(h)

    def test_invalid_args_mutate_nothing(self):
        for bad in (0, -1, float("nan"), float("inf"), True, "5", None):
            with self.assertRaises(InvalidArgument):
                self.e.hold("A", "u1", bad)
        with self.assertRaises(InvalidArgument):
            self.e.hold("", "u1", 5)
        with self.assertRaises(InvalidArgument):
            self.e.hold_many("u1", "ABC", 5)
        with self.assertRaises(InvalidArgument):
            self.e.hold_many("u1", ["A", 3], 5)
        self.assertEqual(self.e.seat_status("A").state, State.FREE)
        self.assertEqual(self.e.audit_holds(), [])

    def test_status_values(self):
        self.assertEqual(self.e.seat_status("A").state, State.FREE)
        self.e.hold("A", "u1", 10)
        s = self.e.seat_status("A")
        self.assertEqual((s.state, s.user, s.expires_at),
                         (State.HELD, "u1", self.clock() + 10))


if __name__ == "__main__":
    unittest.main()
