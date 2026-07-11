"""Balance computation.

Sign convention (used everywhere, including the API):
  net > 0  → the group owes this member (they are a creditor)
  net < 0  → this member owes the group (they are a debtor)

An expense credits the payer with the full base amount and debits each
participant their share. A settlement credits the payer and debits the
payee. Sum of all nets is always zero.

Every number the API reports is reconstructible from the per-expense
ledger returned by member_ledger() — no magic numbers (Rohan's
requirement).
"""
from collections import defaultdict

from ..models import Expense, ExpenseSplit, Settlement


def group_net_balances(group):
    """{member_id: net_minor} for every member of the group."""
    net = defaultdict(int)
    for m in group.members.all():
        net[m.id] = 0
    for e in group.expenses.all():
        net[e.paid_by_id] += e.amount_base_minor
    for s in ExpenseSplit.objects.filter(expense__group=group):
        net[s.member_id] -= s.share_base_minor
    for st in group.settlements.all():
        net[st.payer_id] += st.amount_base_minor
        net[st.payee_id] -= st.amount_base_minor
    return dict(net)


def member_ledger(group, member):
    """Every line that contributes to one member's net balance.

    Returns a list of entries, each with the source object reference and
    the signed effect on the member's net. Their sum equals the member's
    net balance exactly.
    """
    entries = []
    paid = {e.id: e for e in group.expenses.filter(paid_by=member)}
    splits = (
        ExpenseSplit.objects.filter(expense__group=group, member=member)
        .select_related("expense")
    )
    split_by_expense = {s.expense_id: s for s in splits}

    expense_ids = set(paid) | set(split_by_expense)
    for e_id in expense_ids:
        e = paid.get(e_id) or split_by_expense[e_id].expense
        paid_minor = e.amount_base_minor if e_id in paid else 0
        owed_minor = (
            split_by_expense[e_id].share_base_minor if e_id in split_by_expense else 0
        )
        entries.append(
            {
                "type": "expense",
                "expense_id": e.id,
                "date": e.date,
                "description": e.description,
                "currency": e.currency,
                "amount_minor": e.amount_minor,
                "fx_rate": str(e.fx_rate),
                "amount_base_minor": e.amount_base_minor,
                "paid_minor": paid_minor,
                "owed_minor": owed_minor,
                "effect_minor": paid_minor - owed_minor,
            }
        )
    for st in group.settlements.all():
        if st.payer_id == member.id or st.payee_id == member.id:
            effect = st.amount_base_minor if st.payer_id == member.id else -st.amount_base_minor
            entries.append(
                {
                    "type": "settlement",
                    "settlement_id": st.id,
                    "date": st.date,
                    "description": st.note or f"{st.payer.name} paid {st.payee.name}",
                    "paid_minor": st.amount_base_minor if st.payer_id == member.id else 0,
                    "owed_minor": st.amount_base_minor if st.payee_id == member.id else 0,
                    "effect_minor": effect,
                }
            )
    entries.sort(key=lambda x: (x["date"], x.get("expense_id") or 0))
    return entries


def suggest_settlements(net_by_member):
    """Minimal-transfer suggestions: who pays whom (Aisha's requirement).

    Greedy largest-debtor → largest-creditor matching. Deterministic:
    ties break on member id. Returns [{payer_id, payee_id, amount_minor}].
    """
    creditors = sorted(
        ((mid, n) for mid, n in net_by_member.items() if n > 0),
        key=lambda x: (-x[1], x[0]),
    )
    debtors = sorted(
        ((mid, -n) for mid, n in net_by_member.items() if n < 0),
        key=lambda x: (-x[1], x[0]),
    )
    transfers = []
    ci = di = 0
    creditors = [list(c) for c in creditors]
    debtors = [list(d) for d in debtors]
    while ci < len(creditors) and di < len(debtors):
        pay = min(creditors[ci][1], debtors[di][1])
        if pay > 0:
            transfers.append(
                {
                    "payer_id": debtors[di][0],
                    "payee_id": creditors[ci][0],
                    "amount_minor": pay,
                }
            )
        creditors[ci][1] -= pay
        debtors[di][1] -= pay
        if creditors[ci][1] == 0:
            ci += 1
        if debtors[di][1] == 0:
            di += 1
    return transfers
