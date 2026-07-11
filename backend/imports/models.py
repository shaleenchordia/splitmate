"""Staged import models.

An upload creates an ImportBatch in `staged` state: rows are parsed and
anomaly detectors run, but NOTHING touches the ledger. The reviewer
approves or overrides each proposed action, then commits the batch
(Meera's requirement: every change the app makes is approved first).
The committed batch keeps the full report permanently.
"""
from django.conf import settings
from django.db import models


class ImportBatch(models.Model):
    class Status(models.TextChoices):
        STAGED = "staged"
        COMMITTED = "committed"
        DISCARDED = "discarded"

    group = models.ForeignKey("expenses.Group", on_delete=models.CASCADE, related_name="imports")
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    file_name = models.CharField(max_length=255)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.STAGED)
    # FX rates offered/used for this batch, e.g. {"USD": "83.00"}.
    fx_rates = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    committed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Import #{self.id} {self.file_name} ({self.status})"


class ImportRow(models.Model):
    """One CSV row, its parsed interpretation, and its final disposition."""

    class Kind(models.TextChoices):
        EXPENSE = "expense"
        SETTLEMENT = "settlement"
        SKIP = "skip"  # row excluded from the ledger

    batch = models.ForeignKey(ImportBatch, on_delete=models.CASCADE, related_name="rows")
    row_number = models.IntegerField()  # 1-based, matching the file incl. header offset
    raw = models.JSONField()  # original cell values, untouched
    # Parser's proposed interpretation (dates ISO, amounts in minor units,
    # names normalized...). The review UI edits this, never `raw`.
    parsed = models.JSONField(default=dict)
    kind = models.CharField(max_length=12, choices=Kind.choices, default=Kind.EXPENSE)
    needs_review = models.BooleanField(default=False)
    approved = models.BooleanField(default=False)
    created_expense = models.ForeignKey(
        "expenses.Expense", null=True, blank=True, on_delete=models.SET_NULL
    )
    created_settlement = models.ForeignKey(
        "expenses.Settlement", null=True, blank=True, on_delete=models.SET_NULL
    )

    class Meta:
        ordering = ["row_number"]
        constraints = [
            models.UniqueConstraint(fields=["batch", "row_number"], name="unique_row_per_batch")
        ]


class ImportAnomaly(models.Model):
    """A detected data problem on a row: what we found, what we propose,
    and what the reviewer decided. This is the source of the import report."""

    class Severity(models.TextChoices):
        INFO = "info"  # auto-fixable, applied unless overridden
        WARNING = "warning"  # applied by default but worth attention
        REVIEW = "review"  # blocks commit until the reviewer decides

    row = models.ForeignKey(ImportRow, on_delete=models.CASCADE, related_name="anomalies")
    code = models.CharField(max_length=40)  # e.g. DUPLICATE_EXACT, PERCENT_SUM_INVALID
    severity = models.CharField(max_length=8, choices=Severity.choices)
    message = models.TextField()
    proposed_action = models.JSONField()  # {"action": "...", ...params}
    resolved_action = models.JSONField(null=True, blank=True)  # reviewer's final word

    class Meta:
        ordering = ["row__row_number", "id"]

    def final_action(self):
        return self.resolved_action or self.proposed_action
