"""Concurrency-safe seat hold engine. See DECISIONS.md for the semantics.

Lock order (never violated, this is what rules out deadlock):
    user lock  ->  seat locks in sorted seat-id order
``confirm`` / ``release`` / ``seat_status`` take a single seat lock only.
The metadata lock ``_meta`` is a leaf: nothing is acquired while holding it.
"""

from __future__ import annotations

import enum
import math
import threading
import time
from contextlib import ExitStack
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Sequence

from .errors import (
    AlreadySold,
    HoldLimitExceeded,
    HoldLost,
    HoldNotFound,
    HoldReleased,
    InvalidArgument,
    SeatHeld,
    SeatSold,
)

MAX_HOLDS_PER_USER = 4


class State(enum.Enum):
    FREE = "FREE"
    HELD = "HELD"
    SOLD = "SOLD"


@dataclass(frozen=True)
class SeatStatus:
    state: State
    user: Optional[str] = None
    expires_at: Optional[float] = None

    def __repr__(self) -> str:
        if self.state is State.HELD:
            return f"HELD({self.user}, {self.expires_at})"
        if self.state is State.SOLD:
            return f"SOLD({self.user})"
        return "FREE"


class HoldStatus(enum.Enum):
    HELD = "HELD"  # may be lapsed (time passed) but untouched
    SOLD = "SOLD"
    RELEASED = "RELEASED"
    SUPERSEDED = "SUPERSEDED"  # lapsed, then someone created a newer hold


class Hold:
    __slots__ = (
        "id", "seat_id", "user_id", "created_at", "expires_at", "status",
        "created_seq", "closed_seq", "closed_at",
    )

    def __init__(self, id, seat_id, user_id, created_at, expires_at, created_seq):
        self.id = id
        self.seat_id = seat_id
        self.user_id = user_id
        self.created_at = created_at
        self.expires_at = expires_at
        self.status = HoldStatus.HELD
        self.created_seq = created_seq  # global order stamp (audit only)
        self.closed_seq = None          # stamp when sold/released
        self.closed_at = None


class _Seat:
    __slots__ = ("lock", "hold", "sold")

    def __init__(self):
        self.lock = threading.Lock()
        self.hold: Optional[Hold] = None  # current un-closed hold, maybe lapsed
        self.sold: Optional[Hold] = None


class _User:
    __slots__ = ("lock", "holds")

    def __init__(self):
        self.lock = threading.Lock()
        self.holds: List[Hold] = []  # appended only under lock; pruned lazily


class HoldEngine:
    def __init__(self, clock: Callable[[], float] = time.monotonic,
                 max_holds_per_user: int = MAX_HOLDS_PER_USER):
        self._clock = clock
        self._max = max_holds_per_user
        self._meta = threading.Lock()
        self._seats: Dict[str, _Seat] = {}
        self._users: Dict[str, _User] = {}
        self._holds: Dict[str, Hold] = {}
        self._next_id = 0
        self._seq = 0

    # ------------------------------------------------------------------ API

    def hold(self, seat_id: str, user_id: str, ttl_seconds: float) -> str:
        return self.hold_many(user_id, [seat_id], ttl_seconds)[0]

    def hold_many(self, user_id: str, seat_ids: Sequence[str],
                  ttl_seconds: float) -> List[str]:
        """All-or-nothing. Returns hold ids in (de-duplicated) request order."""
        _check_id(user_id, "user_id")
        _check_ttl(ttl_seconds)
        if isinstance(seat_ids, (str, bytes)):
            raise InvalidArgument("seat_ids must be a sequence of seat ids")
        seat_ids = list(seat_ids)
        for sid in seat_ids:
            _check_id(sid, "seat_id")
        seats = list(dict.fromkeys(seat_ids))  # de-dupe, keep order

        user = self._user(user_id)
        seat_objs = {sid: self._seat(sid) for sid in seats}

        with user.lock, ExitStack() as stack:
            for sid in sorted(seats):
                stack.enter_context(seat_objs[sid].lock)
            now = self._clock()

            # Pass 1: validate everything, mutate nothing.
            plan = []  # (seat, existing live hold of this user or None)
            needed = 0
            for sid in seats:
                seat = seat_objs[sid]
                if seat.sold is not None:
                    raise SeatSold(sid)
                cur = seat.hold
                if cur is not None and now < cur.expires_at:
                    if cur.user_id != user_id:
                        raise SeatHeld(sid)
                    plan.append((seat, cur))  # R5: idempotent retry
                else:
                    plan.append((seat, None))
                    needed += 1
            if needed and self._live_count(user, now) + needed > self._max:
                raise HoldLimitExceeded(
                    f"{user_id} would exceed {self._max} holds")

            # Pass 2: apply. Cannot fail from here on.
            expires_at = now + ttl_seconds
            ids = []
            for sid, (seat, existing) in zip(seats, plan):
                if existing is not None:
                    ids.append(existing.id)
                    continue
                if seat.hold is not None:  # lapsed leftover -> now taken
                    seat.hold.status = HoldStatus.SUPERSEDED
                h = self._new_hold(sid, user_id, now, expires_at)
                seat.hold = h
                user.holds.append(h)
                ids.append(h.id)
            return ids

    def confirm(self, hold_id: str) -> bool:
        h = self._lookup(hold_id)
        seat = self._seat(h.seat_id)
        with seat.lock:
            now = self._clock()
            if h.status is HoldStatus.SOLD:
                return True  # D9 idempotent
            if h.status is HoldStatus.RELEASED:
                raise HoldReleased(hold_id)
            if h.status is HoldStatus.SUPERSEDED:
                raise HoldLost(hold_id)
            # HELD: live, or lapsed but nobody has taken the seat (D1).
            assert seat.hold is h and seat.sold is None
            h.status = HoldStatus.SOLD
            h.closed_at = now
            h.closed_seq = self._stamp()
            seat.hold = None
            seat.sold = h
            return True

    def release(self, hold_id: str) -> bool:
        h = self._lookup(hold_id)
        seat = self._seat(h.seat_id)
        with seat.lock:
            now = self._clock()
            if h.status is HoldStatus.RELEASED:
                return True  # D10 idempotent
            if h.status is HoldStatus.SOLD:
                raise AlreadySold(hold_id)
            if h.status is HoldStatus.SUPERSEDED:
                raise HoldLost(hold_id)
            h.status = HoldStatus.RELEASED
            h.closed_at = now
            h.closed_seq = self._stamp()
            seat.hold = None
            return True

    def seat_status(self, seat_id: str) -> SeatStatus:
        _check_id(seat_id, "seat_id")
        with self._meta:
            seat = self._seats.get(seat_id)
        if seat is None:
            return SeatStatus(State.FREE)
        with seat.lock:
            now = self._clock()
            if seat.sold is not None:
                return SeatStatus(State.SOLD, seat.sold.user_id)
            cur = seat.hold
            if cur is not None and now < cur.expires_at:
                return SeatStatus(State.HELD, cur.user_id, cur.expires_at)
            return SeatStatus(State.FREE)

    # ------------------------------------------------- introspection (tests)

    def live_holds(self, user_id: str) -> List[str]:
        """Ids of the user's live holds, read under the user lock (so no new
        hold of this user can appear mid-scan)."""
        user = self._user(user_id)
        with user.lock:
            now = self._clock()
            return [h.id for h in user.holds
                    if h.status is HoldStatus.HELD and now < h.expires_at]

    def audit_holds(self) -> List[Hold]:
        """Every hold ever created (do not mutate)."""
        with self._meta:
            return list(self._holds.values())

    # -------------------------------------------------------------- helpers

    def _live_count(self, user: _User, now: float) -> int:
        # Caller holds user.lock. Prune closed holds; count live ones.
        user.holds = [h for h in user.holds if h.status is HoldStatus.HELD]
        return sum(1 for h in user.holds if now < h.expires_at)

    def _new_hold(self, seat_id, user_id, now, expires_at) -> Hold:
        with self._meta:
            self._next_id += 1
            self._seq += 1
            h = Hold(f"h{self._next_id}", seat_id, user_id, now, expires_at,
                     self._seq)
            self._holds[h.id] = h
            return h

    def _stamp(self) -> int:
        with self._meta:
            self._seq += 1
            return self._seq

    def _lookup(self, hold_id: str) -> Hold:
        with self._meta:
            h = self._holds.get(hold_id) if isinstance(hold_id, str) else None
        if h is None:
            raise HoldNotFound(str(hold_id))
        return h

    def _seat(self, seat_id: str) -> _Seat:
        with self._meta:
            s = self._seats.get(seat_id)
            if s is None:
                s = self._seats[seat_id] = _Seat()
            return s

    def _user(self, user_id: str) -> _User:
        with self._meta:
            u = self._users.get(user_id)
            if u is None:
                u = self._users[user_id] = _User()
            return u


def _check_id(value, name: str) -> None:
    if not isinstance(value, str) or not value:
        raise InvalidArgument(f"{name} must be a non-empty string")


def _check_ttl(ttl) -> None:
    if (isinstance(ttl, bool) or not isinstance(ttl, (int, float))
            or not math.isfinite(ttl) or ttl <= 0):
        raise InvalidArgument("ttl_seconds must be a finite number > 0")
