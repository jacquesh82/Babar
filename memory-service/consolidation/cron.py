"""Parseur/évaluateur cron minimal (5 champs) — sans dépendance externe.

Supporte ``minute hour day-of-month month day-of-week`` avec ``*``, listes
(``,``), plages (``a-b``) et pas (``*/n``, ``a-b/n``). Sémantique day-of-month /
day-of-week alignée sur Vixie cron : si l'un des deux est ``*``, on combine en ET
des champs spécifiés ; si les deux sont spécifiques, on combine en OU.

Utilisé par le worker de consolidation pour planifier ``CONSOLIDATION_CRON``.
"""

from __future__ import annotations

from datetime import datetime, timedelta

# (min, max) inclusifs par champ : minute, heure, jour-mois, mois, jour-semaine.
_RANGES = [(0, 59), (0, 23), (1, 31), (1, 12), (0, 6)]

Cron = list[set[int]]


def _full(idx: int) -> set[int]:
    lo, hi = _RANGES[idx]
    return set(range(lo, hi + 1))


def _parse_field(field: str, idx: int) -> set[int]:
    lo, hi = _RANGES[idx]
    values: set[int] = set()
    for part in field.split(","):
        step = 1
        body = part
        if "/" in body:
            body, step_str = body.split("/", 1)
            step = int(step_str)
            if step <= 0:
                raise ValueError(f"pas invalide : {part!r}")
        if body in ("*", ""):
            start, end = lo, hi
        elif "-" in body:
            a, b = body.split("-", 1)
            start, end = int(a), int(b)
        else:
            start = end = int(body)
        if start < lo or end > hi or start > end:
            raise ValueError(f"champ cron hors bornes : {part!r}")
        values.update(range(start, end + 1, step))
    return values


def parse_cron(expr: str) -> Cron:
    """Compile une expression cron 5 champs en listes de valeurs autorisées."""
    fields = expr.split()
    if len(fields) != 5:
        raise ValueError(f"expression cron invalide (5 champs attendus) : {expr!r}")
    return [_parse_field(fields[i], i) for i in range(5)]


def matches(dt: datetime, cron: Cron) -> bool:
    """Indique si ``dt`` (à la minute) satisfait l'expression cron."""
    minute, hour, dom, month, dow = cron
    if dt.minute not in minute or dt.hour not in hour or dt.month not in month:
        return False
    cron_dow = (dt.weekday() + 1) % 7  # Python: lundi=0 → cron: dimanche=0
    dom_is_star = dom == _full(2)
    dow_is_star = dow == _full(4)
    if dom_is_star or dow_is_star:
        return dt.day in dom and cron_dow in dow
    return dt.day in dom or cron_dow in dow


def next_run(after: datetime, cron: Cron) -> datetime:
    """Prochaine occurrence strictement après ``after`` (résolution minute)."""
    candidate = after.replace(second=0, microsecond=0) + timedelta(minutes=1)
    for _ in range(366 * 24 * 60):  # borne : 1 an
        if matches(candidate, cron):
            return candidate
        candidate += timedelta(minutes=1)
    raise ValueError("aucune occurrence cron dans l'année à venir")


def seconds_until_next(now: datetime, cron: Cron) -> float:
    """Secondes jusqu'à la prochaine occurrence (≥ 0)."""
    return max(0.0, (next_run(now, cron) - now).total_seconds())
