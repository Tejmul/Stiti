"""Day planner: OR-Tools CP-SAT time-blocking (report §Scheduling; benchmarked on this M2:
12 tasks optimal in 10–60 ms, 50 tasks good in 0.5–2 s).

Model: 5-minute slots from now (or 9 AM) to the end of day; each open task is an optional interval.
Maximize Σ value·urgency of scheduled tasks; deadlines are hard where feasible; high-energy tasks
prefer the morning window; already-accepted blocks are penalized for moving. 1 s limit.
Spoken output obeys the ≤3-items rule.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from ortools.sat.python import cp_model

from ..config import CFG
from ..db import q

SLOT = 5  # minutes


def plan_day(now: datetime | None = None, day_end_hour: int = 22, max_tasks: int = 20,
             time_limit_s: float = 1.0) -> list[dict]:
    now = now or datetime.now(CFG.tz)
    nine = now.replace(hour=9, minute=0, second=0, microsecond=0)
    if now.hour >= day_end_hour - 1:          # late: plan tomorrow
        start = nine + timedelta(days=1)
    else:
        start = max(now, nine).replace(second=0, microsecond=0)
        start += timedelta(minutes=(-start.minute) % SLOT)  # round up to the next 5-min slot
    end = start.replace(hour=day_end_hour, minute=0)
    horizon = max(0, int((end - start).total_seconds() // 60 // SLOT))
    if horizon < 3:
        return []
    tasks = q("""SELECT id, title, due, coalesce(est_minutes, 30) est, coalesce(value, 3) value, energy,
                        scheduled
                 FROM tasks WHERE status='open' AND (wait_until IS NULL OR wait_until <= now())
                 ORDER BY due NULLS LAST, coalesce(value,3) DESC, created_at LIMIT %s""", (max_tasks,))
    if not tasks:
        return []
    # fixed blocks: alarms/reminders don't block time; future calendar events will (Phase 6)
    m = cp_model.CpModel()
    morning_end = max(0, int((start.replace(hour=12, minute=0) - start).total_seconds() // 60 // SLOT))
    obj = []
    vars_ = []
    for t in tasks:
        dur = max(1, int(t["est"]) // SLOT)
        if dur > horizon:
            continue
        pres = m.NewBoolVar(f"p{t['id']}")
        s = m.NewIntVar(0, horizon - dur, f"s{t['id']}")
        iv = m.NewOptionalIntervalVar(s, dur, s + dur, pres, f"i{t['id']}")
        urg = 1
        if t["due"]:
            due_slot = int((t["due"] - start).total_seconds() // 60 // SLOT)
            if due_slot < dur:
                urg = 4                       # already due: still schedulable, top priority, no hard bound
            elif due_slot <= horizon:
                urg = 3
                m.Add(s + dur <= due_slot).OnlyEnforceIf(pres)
            else:
                urg = 2 if due_slot <= horizon * 3 else 1
        w = 10_000 * int(t["value"]) * urg       # presence dominates…
        obj.append(w * pres)
        obj.append(-int(t["value"]) * urg * s)    # …tie-break: important things earlier
        if t["energy"] == "high" and morning_end > 0:   # prefer mornings for deep work
            early = m.NewBoolVar(f"e{t['id']}")
            m.Add(s + dur <= morning_end).OnlyEnforceIf(early)
            m.AddImplication(early, pres)
            obj.append(5_000 * early)
        if t["scheduled"]:                               # stability: keep accepted blocks
            prev = int((t["scheduled"] - start).total_seconds() // 60 // SLOT)
            if 0 <= prev <= horizon - dur:
                same = m.NewBoolVar(f"k{t['id']}")
                m.Add(s == prev).OnlyEnforceIf(same)
                obj.append(15_000 * same)
        vars_.append((t, pres, s, dur))
    m.AddNoOverlap([m.NewOptionalIntervalVar(s, d, s + d, p, f"n{t['id']}") for t, p, s, d in vars_])
    m.Maximize(sum(obj))
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_s
    solver.parameters.num_workers = 4
    status = solver.Solve(m)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return []
    plan = []
    for t, p, s, d in vars_:
        if solver.Value(p):
            st = start + timedelta(minutes=solver.Value(s) * SLOT)
            plan.append({"id": t["id"], "title": t["title"], "start": st, "end": st + timedelta(minutes=d * SLOT)})
    plan.sort(key=lambda x: x["start"])
    return plan


def accept(plan: list[dict]) -> None:
    for p in plan:
        q("UPDATE tasks SET scheduled=%s WHERE id=%s", (p["start"], p["id"]))


def speak_plan(plan: list[dict], low_energy: bool = False) -> str:
    if not plan:
        return "Nothing to plan — your list is clear, or the day's almost over."
    if low_energy:  # minimum viable day: the smallest step that still matters
        p = min(plan, key=lambda x: (x["end"] - x["start"], plan.index(x)))  # ties: more important (earlier) wins
        return f"Just one thing: {p['title']} at {p['start']:%I:%M %p}. That's enough for today."
    head = "; ".join(f"{p['start']:%I:%M %p} {p['title']}" for p in plan[:3])
    more = f" Plus {len(plan) - 3} more after that — say “more”." if len(plan) > 3 else ""
    return f"Here's your day: {head}.{more}"
