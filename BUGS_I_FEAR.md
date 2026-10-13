# BUGS_I_FEAR

## The bug class my tests would NOT catch: clock skew / non-monotonic time in production

All my tests use a `FakeClock` that only moves forward and is read consistently.
The engine's whole notion of "expired", "late confirm" and "retaken" hangs off
`clock()`. In production the clock is something like `time.time()` on several app
servers, and the engine here is in-memory and per-process anyway:

- NTP steps the wall clock backwards: a lapsed hold becomes live again, so a seat
  that was FREE (and maybe already given to someone else) shows as HELD, or a
  user sees a hold's `expires_at` jump.
- Two nodes with skewed clocks disagree about whether a hold is expired, which
  produces the one failure the business cares about (two people believing they
  own a seat) as soon as state is shared through a DB/Redis rather than one
  process.

Nothing in my suite can fail on this: the fake clock cannot go backwards (it
raises), and there is only one process.

**How I would catch it in production**
1. Use a monotonic clock for TTL arithmetic within a process; for shared state,
   take time from the store (e.g. DB `now()` / Redis `TIME`), never from app servers.
2. Emit a metric/alert on any observed backwards step (`now < last_seen_now`) and
   on `confirm` of a hold with `closed_at - expires_at` unusually large (late
   confirms are legal here, so a spike is a signal of skew or an abandoned-cart
   problem).
3. A periodic reconciliation job that scans sold seats and asserts the same
   invariants as my stress test (exactly one SOLD per seat; no other hold created
   between a confirmed hold's creation and confirmation), and pages on violation.
   Payments give a second, independent ledger: two successful charges for one seat
   is the canary.

## Smaller things I also fear (not covered)
- **Unbounded memory:** every hold is kept forever (needed for late-confirm /
  superseded semantics). A real deployment needs retention or a DB.
- **Late confirm has no time limit** (D1): a stale hold can be confirmed long
  after the user abandoned it if nobody else wanted the seat.
- **Python-specific:** the stress test cannot prove absence of races, only fail to
  find them; the GIL hides some interleavings (mitigated with a tiny switch
  interval and mutation checks, but not proof).
- **Cap check reads other-seat holds without their seat locks.** I argued it only
  errs toward spurious rejection (holds only shrink concurrently), and the
  tests agree, but it is the subtlest reasoning in the code.
