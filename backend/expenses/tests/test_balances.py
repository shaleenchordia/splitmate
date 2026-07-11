from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase

from expenses.models import Expense, ExpenseSplit, Group, GroupMember, Settlement
from expenses.services.balances import (
    group_net_balances,
    member_ledger,
    suggest_settlements,
)

User = get_user_model()


def make_expense(group, user, payer, amount_base_minor, participants, **kwargs):
    expense = Expense.objects.create(
        group=group,
        description=kwargs.get("description", "test"),
        date=kwargs.get("date", date(2026, 2, 1)),
        paid_by=payer,
        currency=kwargs.get("currency", "INR"),
        amount_minor=kwargs.get("amount_minor", amount_base_minor),
        fx_rate=kwargs.get("fx_rate", 1),
        amount_base_minor=amount_base_minor,
        split_type="equal",
        created_by=user,
    )
    share = amount_base_minor // len(participants)
    remainder = amount_base_minor - share * len(participants)
    for i, member in enumerate(participants):
        ExpenseSplit.objects.create(
            expense=expense,
            member=member,
            share_base_minor=share + (1 if i < remainder else 0),
        )
    return expense


class BalanceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("u", password="passw0rd1")
        self.group = Group.objects.create(name="Flat", created_by=self.user)
        self.a = GroupMember.objects.create(group=self.group, name="A")
        self.b = GroupMember.objects.create(group=self.group, name="B")
        self.c = GroupMember.objects.create(group=self.group, name="C")

    def test_payer_credited_participants_debited(self):
        make_expense(self.group, self.user, self.a, 3000, [self.a, self.b, self.c])
        net = group_net_balances(self.group)
        self.assertEqual(net[self.a.id], 2000)  # paid 3000, owes 1000
        self.assertEqual(net[self.b.id], -1000)
        self.assertEqual(net[self.c.id], -1000)
        self.assertEqual(sum(net.values()), 0)

    def test_settlement_reduces_debt(self):
        make_expense(self.group, self.user, self.a, 3000, [self.a, self.b, self.c])
        Settlement.objects.create(
            group=self.group,
            payer=self.b,
            payee=self.a,
            amount_base_minor=1000,
            date=date(2026, 2, 2),
            created_by=self.user,
        )
        net = group_net_balances(self.group)
        self.assertEqual(net[self.b.id], 0)
        self.assertEqual(net[self.a.id], 1000)
        self.assertEqual(sum(net.values()), 0)

    def test_payer_not_in_split_owes_nothing(self):
        # Birthday cake pattern: payer covers others, isn't a participant.
        make_expense(self.group, self.user, self.a, 1500, [self.b, self.c])
        net = group_net_balances(self.group)
        self.assertEqual(net[self.a.id], 1500)
        self.assertEqual(net[self.b.id], -750)

    def test_ledger_reconstructs_net_exactly(self):
        make_expense(self.group, self.user, self.a, 3000, [self.a, self.b, self.c])
        make_expense(self.group, self.user, self.b, 999, [self.a, self.b])
        Settlement.objects.create(
            group=self.group,
            payer=self.c,
            payee=self.a,
            amount_base_minor=500,
            date=date(2026, 2, 3),
            created_by=self.user,
        )
        net = group_net_balances(self.group)
        for member in (self.a, self.b, self.c):
            entries = member_ledger(self.group, member)
            self.assertEqual(
                sum(e["effect_minor"] for e in entries),
                net[member.id],
                f"ledger does not reconcile for {member.name}",
            )

    def test_refund_flows_backwards(self):
        make_expense(self.group, self.user, self.a, -900, [self.a, self.b, self.c])
        net = group_net_balances(self.group)
        self.assertEqual(net[self.a.id], -600)  # returned 900, gets back 300
        self.assertEqual(net[self.b.id], 300)


class SettleUpTests(TestCase):
    def test_transfers_zero_all_balances(self):
        net = {1: 105310, 2: -60559, 3: -44751, 4: 0}
        transfers = suggest_settlements(net)
        for t in transfers:
            net[t["payer_id"]] += t["amount_minor"]
            net[t["payee_id"]] -= t["amount_minor"]
        self.assertTrue(all(v == 0 for v in net.values()))

    def test_at_most_n_minus_1_transfers(self):
        net = {1: 500, 2: 300, 3: -200, 4: -600, 5: 0}
        self.assertLessEqual(len(suggest_settlements(net)), 4)

    def test_empty_when_settled(self):
        self.assertEqual(suggest_settlements({1: 0, 2: 0}), [])
