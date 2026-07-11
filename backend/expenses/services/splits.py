"""Split allocation.

All allocation happens in integer minor units (paise). Fractional ideal
shares are settled with the largest-remainder method so the allocated
shares ALWAYS sum exactly to the expense total — no lost or invented
paise. Ties on remainder break by participant input order, which makes
the result deterministic and easy to reproduce by hand in a review.

Refunds are negative expenses: we allocate the absolute value the same
way, then negate every share.
"""
from fractions import Fraction


class SplitError(ValueError):
    pass


def _allocate_by_weights(total_minor, weights):
    """Distribute total_minor across weights (list of Fraction), exactly.

    Returns a list of ints summing to total_minor.
    """
    if not weights:
        raise SplitError("no participants to split across")
    weight_sum = sum(weights)
    if weight_sum <= 0:
        raise SplitError("split weights must sum to a positive value")

    sign = -1 if total_minor < 0 else 1
    total = abs(total_minor)

    ideals = [Fraction(total) * w / weight_sum for w in weights]
    floors = [int(i) for i in ideals]  # Fraction.__int__ truncates toward zero
    remainder = total - sum(floors)
    # Hand out the leftover minor units to the largest fractional parts;
    # ties resolve by input order (stable sort).
    order = sorted(range(len(weights)), key=lambda i: ideals[i] - floors[i], reverse=True)
    shares = floors[:]
    for i in order[:remainder]:
        shares[i] += 1
    return [sign * s for s in shares]


def split_equal(total_minor, participant_ids):
    weights = [Fraction(1)] * len(participant_ids)
    shares = _allocate_by_weights(total_minor, weights)
    return dict(zip(participant_ids, shares))


def split_percentage(total_minor, percent_by_id):
    """percent_by_id: {id: Decimal percent}.

    Percents must sum to 100 within a 0.01-point tolerance. The slack
    exists because a normalized bad sum (e.g. 110% scaled down) rounds
    to values like 27.2727 that can't hit 100 exactly at 4 decimals;
    allocation is proportional to the weights, so the result is still
    exact to the paisa. A genuinely wrong sum (90, 110) is rejected.
    """
    ids = list(percent_by_id)
    percents = [Fraction(str(percent_by_id[i])) for i in ids]
    if abs(sum(percents) - 100) > Fraction(1, 100):
        raise SplitError(f"percentages sum to {float(sum(percents))}, expected 100")
    shares = _allocate_by_weights(total_minor, percents)
    return dict(zip(ids, shares))


def split_share(total_minor, units_by_id):
    """units_by_id: {id: int share units}, e.g. Rohan 2; Priya 1."""
    ids = list(units_by_id)
    units = [Fraction(units_by_id[i]) for i in ids]
    if any(u < 0 for u in units):
        raise SplitError("share units cannot be negative")
    shares = _allocate_by_weights(total_minor, units)
    return dict(zip(ids, shares))


def split_unequal(total_minor, amount_minor_by_id):
    """Exact amounts; must sum to the expense total."""
    s = sum(amount_minor_by_id.values())
    if s != total_minor:
        raise SplitError(
            f"unequal split amounts sum to {s}, expected {total_minor}"
        )
    return dict(amount_minor_by_id)


def compute_splits(split_type, total_minor, participants):
    """participants: list of dicts with keys
    member_id, and per type: percent | units | amount_minor.

    Returns {member_id: share_minor} summing exactly to total_minor.
    """
    ids = [p["member_id"] for p in participants]
    if len(set(ids)) != len(ids):
        raise SplitError("duplicate participant in split")
    if split_type == "equal":
        return split_equal(total_minor, ids)
    if split_type == "percentage":
        return split_percentage(total_minor, {p["member_id"]: p["percent"] for p in participants})
    if split_type == "share":
        return split_share(total_minor, {p["member_id"]: p["units"] for p in participants})
    if split_type == "unequal":
        return split_unequal(
            total_minor, {p["member_id"]: p["amount_minor"] for p in participants}
        )
    raise SplitError(f"unknown split type: {split_type}")
