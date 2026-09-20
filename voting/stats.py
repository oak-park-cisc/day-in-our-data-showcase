from __future__ import annotations

from math import sqrt


def average_ranks(values: dict[str, float], higher_is_better: bool = True) -> dict[str, float]:
    """Rank 1 is best. Tied values share the average of the ranks they span."""
    items = sorted(values.items(), key=lambda kv: -kv[1] if higher_is_better else kv[1])
    ranks: dict[str, float] = {}
    i = 0
    while i < len(items):
        j = i
        while j + 1 < len(items) and items[j + 1][1] == items[i][1]:
            j += 1
        shared = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[items[k][0]] = shared
        i = j + 1
    return ranks


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    vx = sqrt(sum((x - mx) ** 2 for x in xs))
    vy = sqrt(sum((y - my) ** 2 for y in ys))
    if vx == 0 or vy == 0:
        return None
    return cov / (vx * vy)


def spearman(a: dict[str, float], b: dict[str, float]) -> float | None:
    """Pearson correlation on average ranks, so ties are handled correctly."""
    keys = sorted(set(a) & set(b))
    if len(keys) < 2:
        return None
    ra = average_ranks({k: a[k] for k in keys})
    rb = average_ranks({k: b[k] for k in keys})
    return _pearson([ra[k] for k in keys], [rb[k] for k in keys])
