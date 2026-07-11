"""Core domain models.

Money is stored as integer minor units (paise for INR, cents for USD) to
avoid float drift. Every expense keeps its original currency amount AND
the converted base-currency amount, with the FX rate that was applied,
so conversions are always traceable (Priya's requirement).
"""
from django.conf import settings
from django.db import models


class Group(models.Model):
    name = models.CharField(max_length=120)
    base_currency = models.CharField(max_length=3, default="INR")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="groups_created"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class GroupMember(models.Model):
    """A person in a group. Not necessarily a registered app user.

    joined_on / left_on bound the membership window: an expense dated
    outside a participant's window is flagged (Sam's requirement).
    Null joined_on = member since group creation; null left_on = still active.
    """

    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name="members")
    name = models.CharField(max_length=80)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="memberships",
    )
    joined_on = models.DateField(null=True, blank=True)
    left_on = models.DateField(null=True, blank=True)
    is_guest = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["group", "name"], name="unique_member_name_per_group")
        ]

    def __str__(self):
        return f"{self.name} ({self.group.name})"

    def is_active_on(self, date):
        if self.joined_on and date < self.joined_on:
            return False
        if self.left_on and date > self.left_on:
            return False
        return True


class Expense(models.Model):
    class SplitType(models.TextChoices):
        EQUAL = "equal"
        UNEQUAL = "unequal"  # exact amounts per participant
        PERCENTAGE = "percentage"
        SHARE = "share"  # proportional units, e.g. Rohan 2; Priya 1

    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name="expenses")
    description = models.CharField(max_length=255)
    date = models.DateField()
    paid_by = models.ForeignKey(
        GroupMember, on_delete=models.PROTECT, related_name="expenses_paid"
    )
    # Original currency as entered.
    currency = models.CharField(max_length=3)
    amount_minor = models.BigIntegerField()  # negative = refund
    # Conversion applied at entry/import time; 1 for base-currency expenses.
    fx_rate = models.DecimalField(max_digits=12, decimal_places=6, default=1)
    amount_base_minor = models.BigIntegerField()
    split_type = models.CharField(max_length=12, choices=SplitType.choices)
    notes = models.TextField(blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="expenses_created"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    # Provenance: set when this expense came from a CSV import.
    source_batch = models.ForeignKey(
        "imports.ImportBatch",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="expenses",
    )
    source_row_number = models.IntegerField(null=True, blank=True)

    class Meta:
        ordering = ["date", "id"]

    def __str__(self):
        return f"{self.date} {self.description} {self.amount_minor / 100} {self.currency}"


class ExpenseSplit(models.Model):
    """One participant's owed share of an expense, in base-currency minor
    units. Raw split inputs (percent / share units / exact amount) are kept
    for traceability so the drill-down can show *why* the share is what it
    is (Rohan's requirement)."""

    expense = models.ForeignKey(Expense, on_delete=models.CASCADE, related_name="splits")
    member = models.ForeignKey(GroupMember, on_delete=models.PROTECT, related_name="splits")
    share_base_minor = models.BigIntegerField()
    input_percent = models.DecimalField(max_digits=7, decimal_places=4, null=True, blank=True)
    input_share_units = models.IntegerField(null=True, blank=True)
    input_amount_minor = models.BigIntegerField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["expense", "member"], name="one_split_per_member")
        ]

    def __str__(self):
        return f"{self.member.name}: {self.share_base_minor / 100}"


class Settlement(models.Model):
    """A payment between two members that reduces debt. Base currency only."""

    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name="settlements")
    payer = models.ForeignKey(
        GroupMember, on_delete=models.PROTECT, related_name="settlements_paid"
    )
    payee = models.ForeignKey(
        GroupMember, on_delete=models.PROTECT, related_name="settlements_received"
    )
    amount_base_minor = models.BigIntegerField()
    date = models.DateField()
    note = models.CharField(max_length=255, blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="settlements_created"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    source_batch = models.ForeignKey(
        "imports.ImportBatch",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="settlements",
    )
    source_row_number = models.IntegerField(null=True, blank=True)

    class Meta:
        ordering = ["date", "id"]

    def __str__(self):
        return f"{self.payer.name} -> {self.payee.name}: {self.amount_base_minor / 100}"
