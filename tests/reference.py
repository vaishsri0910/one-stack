"""Deliberately dumb single-threaded reference model.

No locks, no per-seat state: everything is derived by scanning the full list of
holds ever created. The late-confirm rule is expressed differently from the
engine on purpose: a hold is confirmable iff it was not released and *no hold
with a later creation index exists on that seat* (nobody took the seat since).
"""


class RefEngine:
    def __init__(self, clock, max_holds=4):
        self.clock = clock
        self.max = max_holds
        self.holds = []  # dicts, in creation order

    # each returns ("ok", value) or ("err", code)
    def _live(self, h, now):
        return h["state"] == "held" and now < h["exp"]

    def hold_many(self, user, seats, ttl):
        if ttl <= 0:
            return ("err", "INVALID_ARGUMENT")
        now = self.clock()
        seats = list(dict.fromkeys(seats))
        need = []
        for s in seats:
            if any(h["seat"] == s and h["state"] == "sold" for h in self.holds):
                return ("err", "SEAT_SOLD")
            live = [h for h in self.holds if h["seat"] == s and self._live(h, now)]
            if live and live[0]["user"] != user:
                return ("err", "SEAT_HELD")
            if not live:
                need.append(s)
        mine = sum(1 for h in self.holds
                   if h["user"] == user and self._live(h, now))
        if need and mine + len(need) > self.max:
            return ("err", "HOLD_LIMIT_EXCEEDED")
        out = []
        for s in seats:
            live = [h for h in self.holds if h["seat"] == s and self._live(h, now)]
            if live:
                out.append(live[0]["id"])
                continue
            h = dict(id=f"h{len(self.holds) + 1}", seat=s, user=user,
                     exp=now + ttl, state="held")
            self.holds.append(h)
            out.append(h["id"])
        return ("ok", out)

    def hold(self, seat, user, ttl):
        r = self.hold_many(user, [seat], ttl)
        return ("ok", r[1][0]) if r[0] == "ok" else r

    def _find(self, hid):
        for h in self.holds:
            if h["id"] == hid:
                return h
        return None

    def confirm(self, hid):
        h = self._find(hid)
        if h is None:
            return ("err", "HOLD_NOT_FOUND")
        if h["state"] == "sold":
            return ("ok", True)
        if h["state"] == "released":
            return ("err", "HOLD_RELEASED")
        idx = self.holds.index(h)
        if any(o["seat"] == h["seat"] for o in self.holds[idx + 1:]):
            return ("err", "HOLD_LOST")
        h["state"] = "sold"
        return ("ok", True)

    def release(self, hid):
        h = self._find(hid)
        if h is None:
            return ("err", "HOLD_NOT_FOUND")
        if h["state"] == "released":
            return ("ok", True)
        if h["state"] == "sold":
            return ("err", "ALREADY_SOLD")
        idx = self.holds.index(h)
        if any(o["seat"] == h["seat"] for o in self.holds[idx + 1:]):
            return ("err", "HOLD_LOST")
        h["state"] = "released"
        return ("ok", True)

    def seat_status(self, seat):
        now = self.clock()
        for h in self.holds:
            if h["seat"] == seat and h["state"] == "sold":
                return ("SOLD", h["user"], None)
        for h in self.holds:
            if h["seat"] == seat and self._live(h, now):
                return ("HELD", h["user"], h["exp"])
        return ("FREE", None, None)
