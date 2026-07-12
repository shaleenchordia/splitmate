"""Seed a realistic demo group into the database.

Usage:
    python manage.py seed_demo                 # owner defaults to 'aisha'
    python manage.py seed_demo --owner bob --group-name "Demo Flat"

Re-running deletes and recreates the same-named group, so it's safe to
refresh. Everything is generated at run time (dates spread over the last
five months relative to today) and written through the normal models +
split service — no fixtures baked into the app code.
"""
import random
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from expenses.models import Expense, ExpenseSplit, Group, GroupMember, Settlement
from expenses.services import splits as split_service

# (description, note, amount range in ₹, currency, split_type, cadence)
# cadence: 'monthly' repeats each month; 'random' scatters occurrences.
TEMPLATES = [
    ("Monthly rent", "", (48000, 48000), "INR", "share", "monthly"),
    ("Electricity bill", "", (1400, 2600), "INR", "equal", "monthly"),
    ("Wifi broadband", "ACT 300mbps", (999, 999), "INR", "equal", "monthly"),
    ("Netflix subscription", "", (649, 649), "INR", "equal", "monthly"),
    ("Groceries — BigBasket", "", (1800, 3400), "INR", "equal", "random"),
    ("Groceries — Blinkit top-up", "", (400, 900), "INR", "equal", "random"),
    ("Dinner at Truffles", "", (900, 1600), "INR", "equal", "random"),
    ("Swiggy — biryani night", "", (700, 1200), "INR", "equal", "random"),
    ("Sunday brunch", "", (1100, 2000), "INR", "percentage", "random"),
    ("Uber to airport", "", (450, 700), "INR", "equal", "random"),
    ("Cab to office party", "", (300, 500), "INR", "unequal", "random"),
    ("Movie night — PVR", "", (800, 1400), "INR", "equal", "random"),
    ("House cleaning service", "", (1200, 1200), "INR", "equal", "monthly"),
    ("Gas cylinder refill", "", (1100, 1100), "INR", "equal", "random"),
    ("Team dinner (visiting friend)", "paid in dollars", (30, 55), "USD", "equal", "random"),
]

USD_RATE = Decimal("84.20")


class Command(BaseCommand):
    help = "Create (or refresh) a demo group full of generated expenses."

    def add_arguments(self, parser):
        parser.add_argument("--owner", default="aisha", help="username that owns the group")
        parser.add_argument("--group-name", default="Demo Flat 7B")
        parser.add_argument("--seed", type=int, default=None,
                            help="RNG seed for reproducible data (default: random)")

    @transaction.atomic
    def handle(self, *args, **opts):
        User = get_user_model()
        try:
            owner = User.objects.get(username=opts["owner"])
        except User.DoesNotExist:
            raise CommandError(
                f"User '{opts['owner']}' does not exist — register in the app first "
                "or pass --owner <username>."
            )
        rng = random.Random(opts["seed"])

        name = opts["group_name"]
        deleted, _ = Group.objects.filter(name=name, created_by=owner).delete()
        if deleted:
            self.stdout.write(f"Removed previous '{name}'.")

        group = Group.objects.create(name=name, base_currency="INR", created_by=owner)
        today = date.today()
        start = (today.replace(day=1) - timedelta(days=125)).replace(day=1)

        aisha = GroupMember.objects.create(group=group, name="Aisha", user=owner)
        rohan = GroupMember.objects.create(group=group, name="Rohan")
        priya = GroupMember.objects.create(group=group, name="Priya")
        # Sam moves out partway through → departure-window logic is visible.
        sam_left = start + timedelta(days=70)
        sam = GroupMember.objects.create(group=group, name="Sam", left_on=sam_left)
        # A guest shows up in a couple of dinners.
        vikram = GroupMember.objects.create(group=group, name="Vikram", is_guest=True)
        core = [aisha, rohan, priya]

        def active_on(d):
            return [m for m in core + [sam] if m.is_active_on(d)]

        def make_expense(desc, note, amount_major, currency, split_type, d, participants):
            payer = rng.choice(participants if rng.random() < 0.8 else active_on(d))
            fx = USD_RATE if currency == "USD" else Decimal("1")
            amount_minor = round(amount_major * 100)
            amount_base_minor = round(amount_minor * float(fx))
            entries = []
            for i, m in enumerate(participants):
                e = {"member_id": m.id}
                if split_type == "percentage":
                    # first participant carries the remainder to hit 100
                    share = round(100 / len(participants), 2)
                    e["percent"] = (
                        round(100 - share * (len(participants) - 1), 2) if i == 0 else share
                    )
                elif split_type == "share":
                    e["units"] = 2 if i == 0 else 1  # master bedroom pays more
                elif split_type == "unequal":
                    base = amount_base_minor // len(participants)
                    e["amount_minor"] = (
                        amount_base_minor - base * (len(participants) - 1) if i == 0 else base
                    )
                entries.append(e)
            shares = split_service.compute_splits(split_type, amount_base_minor, entries)
            expense = Expense.objects.create(
                group=group, description=desc, date=d, paid_by=payer,
                currency=currency, amount_minor=amount_minor, fx_rate=fx,
                amount_base_minor=amount_base_minor, split_type=split_type,
                notes=note, created_by=owner,
            )
            for e in entries:
                ExpenseSplit.objects.create(
                    expense=expense, member_id=e["member_id"],
                    share_base_minor=shares[e["member_id"]],
                    input_percent=e.get("percent"),
                    input_share_units=e.get("units"),
                    input_amount_minor=e.get("amount_minor"),
                )
            return expense

        n_expenses = 0
        month_firsts = []
        d = start
        while d <= today:
            month_firsts.append(d)
            d = (d + timedelta(days=32)).replace(day=1)

        for desc, note, (lo, hi), currency, split_type, cadence in TEMPLATES:
            if cadence == "monthly":
                occurrences = [
                    m + timedelta(days=rng.randint(0, 5)) for m in month_firsts
                ]
            else:
                occurrences = [
                    start + timedelta(days=rng.randint(0, (today - start).days))
                    for _ in range(rng.randint(2, 4))
                ]
            for occ in occurrences:
                if occ > today:
                    continue
                participants = active_on(occ)
                # guest joins some dinners
                if "Dinner" in desc and rng.random() < 0.5:
                    participants = participants + [vikram]
                amount = rng.uniform(lo, hi) if lo != hi else lo
                make_expense(desc, note, round(amount, 2), currency, split_type, occ, participants)
                n_expenses += 1

        # A refund: the landlord returned part of a maintenance charge.
        make_expense(
            "Maintenance refund from landlord", "refund of over-charge",
            -1500, "INR", "equal", today - timedelta(days=20), core,
        )
        n_expenses += 1

        # A few settlements so balances show movement.
        n_settlements = 0
        for payer, payee, amt, days_ago in [
            (rohan, aisha, 8000, 45),
            (priya, aisha, 5500, 30),
            (sam, aisha, 3000, (today - sam_left).days),
        ]:
            Settlement.objects.create(
                group=group, payer=payer, payee=payee,
                amount_base_minor=amt * 100,
                date=today - timedelta(days=days_ago),
                note="UPI transfer", created_by=owner,
            )
            n_settlements += 1

        self.stdout.write(self.style.SUCCESS(
            f"Seeded '{name}' (group #{group.id}): 5 members, "
            f"{n_expenses} expenses across {len(month_firsts)} months, "
            f"{n_settlements} settlements. Log in as '{owner.username}' to explore."
        ))
