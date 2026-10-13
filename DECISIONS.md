# DECISIONS

Every ambiguity I hit, what I chose, and why. Written before the engine; each
decision that affects behaviour is pinned by a named test (see `tests/`).

## The rule conflicts

### D1. R3 ("late confirm allowed") vs R4 ("never extended")
Conflict: if an expired hold can still be confirmed, the hold has effectively been
extended.

**Choice:** a hold's `expires_at` is immutable. Expiry only means *the seat becomes
available to everyone else*. A lapsed hold keeps a latent right to be confirmed
for as long as **no other hold has been created on that seat since**. Confirming
a lapsed hold is a *sale*, not an extension: nothing about the hold's deadline
changes, and nothing blocks anybody else while it is lapsed.

- `seat_status` of a lapsed seat is `FREE` (it really is takeable).
- The moment anyone (including the same user, see D3) creates a new hold on the
  seat, the old hold becomes `SUPERSEDED` and can never be confirmed, even if the
  newer hold is later released or expires. "Taken in the meantime" means *taken*,
  not "currently held".
- Late confirm does not need a free slot under R2: a confirm turns a hold into a
  sale, and sales are not holds.
- There is no upper bound on how late a confirm can be (spec gives none). Risk: a
  hold from days ago can be confirmed if nobody wanted the seat. A `grace` limit
  would be a one-line change in `confirm`; I did not add a number the spec
  doesn't give.

Tests: `test_late_confirm_allowed_if_untouched`, `test_late_confirm_rejected_if_retaken`,
`test_retaken_then_released_still_lost`, `test_expires_at_never_changes`.

### D2. R5 (idempotent re-hold) vs R4 (never extended)
A retry of `hold()` on a seat I already hold must not be a back door to extend.

**Choice:** a retry returns the **same hold_id with the original `expires_at`**; the
`ttl_seconds` of the retry is ignored. Tests: `test_retry_returns_same_hold_ignores_ttl`.

### D3. R5 vs R3 — retry *after* the hold expired
Is `hold()` on my own lapsed hold a "retry" (return the dead hold id) or new?

**Choice:** once expired it is no longer "a seat I hold" — the seat is FREE. The call
creates a **new hold** with a new id and new TTL (and supersedes the old one).
This is not an extension of the old hold: it is a fresh acquisition, subject to
all checks (R2 included), and it would have failed if someone else had got there
first. Returning an expired id as success would hand the client a hold that
`seat_status` says is not held.

### D4. R5 vs R2 — a retry at the 4-hold limit
**Choice:** idempotency is evaluated *first*. A user at 4 holds retrying one of
those 4 seats succeeds (no new hold is created, so the count does not move).

### D5. R2 vs R6 — how does `hold_many` count against the limit?
**Choice:**
- Duplicate seats in the request are de-duplicated (order kept).
- Seats the user already holds (live) are idempotent (R5) and cost 0 against the limit.
- The rule is: `live_holds(user) + (number of seats needing a new hold) <= 4`,
  checked for the whole batch. If it fails, **nothing** is held (all-or-nothing).
  So `hold_many` of 5 distinct new seats always fails, even for a user with 0 holds.
- If a seat is unavailable *and* the limit would be exceeded, the unavailable-seat
  error wins (checked first, in request order), then the limit error.
- Return value: list of hold_ids in request (de-duplicated) order. Empty list → `[]`.
- Single `hold` is literally `hold_many` with one seat, so the two can't drift apart.

### D6. R2: what counts as "a hold"?
Only **live** holds (not expired, not released, not confirmed). Expired holds
free the quota (otherwise a slow user is locked out of buying anything).
Confirmed seats do not count: R2 limits *holds*, not purchases.

## Other ambiguities

| # | Question | Choice |
|---|----------|--------|
| D7 | Expiry boundary | Live iff `now < expires_at`. At `now == expires_at` it is expired. |
| D8 | Lazy vs eager expiry | Lazy. Liveness is computed from the clock on every operation, so there are no sweeper threads and results can't depend on when a sweep ran. |
| D9 | `confirm` twice | Idempotent `ok` (flaky network, same spirit as R5). |
| D10 | `release` twice | Idempotent `ok`. |
| D11 | `release` of a sold hold | Error `AlreadySold` (a sale can't be undone by the hold API). |
| D12 | `confirm` after `release` | Error `HoldReleased`. |
| D13 | `release` of a lapsed (untouched) hold | `ok`; it gives up the latent late-confirm right. |
| D14 | `confirm`/`release` of superseded hold | Error `HoldLost`. |
| D15 | Unknown hold id | Error `HoldNotFound`. |
| D16 | Invalid input (`ttl <= 0`, NaN/inf, non-str ids, bool ttl) | `InvalidArgument`, nothing mutated. |
| D17 | Unknown seat ids | Seats are created lazily; the engine has no inventory concept. A real system would validate seat ids against the event's seat map. |
| D18 | Clock | Injected callable returning seconds (float). Assumed **monotonic**. Each operation reads the clock once, *after* taking its locks. |
| D19 | Errors | Exceptions deriving from `EngineError`, each with a stable `.code` string. |
| D20 | Hold ids | `h1, h2, ...`, allocated only on success. Holds are kept in memory forever (needed for D1 supersede/late-confirm semantics); no GC. |

## Concurrency design (summary; details in README)
- One lock per seat, one lock per user.
- Lock order is always: **user lock → seat locks in sorted seat-id order**. `confirm`,
  `release`, `seat_status` only ever take one seat lock. Nothing takes a second user
  lock, so there is no cycle, hence no deadlock for overlapping `hold_many` in
  opposite order (they both lock in sorted order).
- The user lock serialises a user's own `hold` calls, making the R2 check-then-insert
  atomic. Holds of a user can only *shrink* concurrently (release/confirm/time), so a
  count read under the user lock is never lower than the truth: the worst case is a
  spurious rejection racing a release, never exceeding 4.
- A global metadata lock guards only the dict registries/counters and is never held
  while waiting for another lock.
