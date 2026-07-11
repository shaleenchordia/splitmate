"""The import pipeline exercised against the REAL assignment file —
every one of these anomalies exists in expenses_export.csv and must be
detected, surfaced, and handled per documented policy (SCOPE.md)."""
from datetime import date
from pathlib import Path

from django.contrib.auth import get_user_model
from django.test import TestCase

from expenses.models import Expense, Group, GroupMember, Settlement
from expenses.services.balances import group_net_balances
from imports.models import ImportAnomaly, ImportBatch, ImportRow
from imports.services import committer, pipeline

User = get_user_model()

DATA = Path(__file__).resolve().parents[3] / "data" / "expenses_export.csv"


def build_flat_group(user):
    group = Group.objects.create(name="Flat 42", base_currency="INR", created_by=user)
    GroupMember.objects.create(group=group, name="Aisha", joined_on=date(2026, 2, 1), user=user)
    GroupMember.objects.create(group=group, name="Rohan", joined_on=date(2026, 2, 1))
    GroupMember.objects.create(group=group, name="Priya", joined_on=date(2026, 2, 1))
    GroupMember.objects.create(
        group=group, name="Meera", joined_on=date(2026, 2, 1), left_on=date(2026, 3, 31)
    )
    GroupMember.objects.create(group=group, name="Sam", joined_on=date(2026, 4, 8))
    GroupMember.objects.create(
        group=group, name="Dev", joined_on=date(2026, 2, 8), is_guest=True
    )
    return group


class AnnexDetectionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("aisha", password="passw0rd1")
        cls.group = build_flat_group(cls.user)
        cls.batch = ImportBatch.objects.create(
            group=cls.group,
            uploaded_by=cls.user,
            file_name="expenses_export.csv",
            fx_rates={"USD": "83.00"},
        )
        with open(DATA, "rb") as f:
            raw_rows = pipeline.read_rows(f, "expenses_export.csv")
        assert len(raw_rows) == 42
        pipeline.stage_batch(cls.batch, raw_rows)

    def anomalies(self, code=None):
        qs = ImportAnomaly.objects.filter(row__batch=self.batch)
        return qs.filter(code=code) if code else qs

    def assert_flagged(self, row_number, code):
        self.assertTrue(
            self.anomalies(code).filter(row__row_number=row_number).exists(),
            f"expected {code} on row {row_number}; got "
            f"{[(a.row.row_number, a.code) for a in self.anomalies()]}",
        )

    # --- one assertion per deliberate data problem ---

    def test_exact_duplicate_marina_bites(self):
        self.assert_flagged(6, "DUPLICATE_EXACT")  # 'dinner - marina bites'

    def test_conflicting_duplicate_thalassa(self):
        # Row 25's note says Aisha's row 24 is wrong -> row 24 proposed out.
        self.assert_flagged(24, "DUPLICATE_SUSPECT")
        self.assert_flagged(25, "DUPLICATE_SUSPECT_KEPT")

    def test_name_variants_normalized(self):
        self.assert_flagged(9, "NAME_VARIANT")  # 'priya'
        self.assert_flagged(11, "NAME_VARIANT")  # 'Priya S'
        self.assert_flagged(27, "NAME_VARIANT")  # 'rohan ' (trailing space)

    def test_fractional_paise_rounded(self):
        self.assert_flagged(10, "FRACTIONAL_MINOR_UNITS")  # 899.995
        row = ImportRow.objects.get(batch=self.batch, row_number=10)
        self.assertEqual(row.parsed["amount_minor"], 90000)  # half-even -> 900.00

    def test_missing_payer(self):
        self.assert_flagged(13, "MISSING_PAYER")

    def test_settlement_logged_as_expense(self):
        self.assert_flagged(14, "SETTLEMENT_AS_EXPENSE")
        a = self.anomalies("SETTLEMENT_AS_EXPENSE").get()
        self.assertEqual(a.proposed_action["payer"], "Rohan")
        self.assertEqual(a.proposed_action["payee"], "Aisha")

    def test_percentages_sum_110(self):
        self.assert_flagged(15, "PERCENT_SUM_INVALID")
        self.assert_flagged(32, "PERCENT_SUM_INVALID")

    def test_usd_rows_converted_at_visible_rate(self):
        for row_number in (20, 21, 23, 26):
            self.assert_flagged(row_number, "FOREIGN_CURRENCY")
        villa = ImportRow.objects.get(batch=self.batch, row_number=20)
        self.assertEqual(villa.parsed["amount_base_minor"], 4482000)  # 540 * 83
        self.assertEqual(villa.parsed["fx_rate"], "83.00")

    def test_unknown_guest_kabir(self):
        self.assert_flagged(23, "UNKNOWN_PERSON")
        a = self.anomalies("UNKNOWN_PERSON").filter(row__row_number=23).get()
        self.assertEqual(a.proposed_action["name"], "Kabir")
        self.assertTrue(a.proposed_action["is_guest"])
        self.assertEqual(a.severity, ImportAnomaly.Severity.REVIEW)

    def test_negative_amount_is_refund_review(self):
        self.assert_flagged(26, "NEGATIVE_AMOUNT")

    def test_year_typo_2014(self):
        self.assert_flagged(27, "DATE_FAR_PAST")
        a = self.anomalies("DATE_FAR_PAST").get()
        self.assertEqual(a.proposed_action, {"action": "set_date", "date": "2026-03-01"})

    def test_2014_row_does_not_cascade_membership_flags(self):
        # Window checks must use the proposed corrected date, or the typo
        # would spuriously flag all four participants.
        self.assertFalse(
            self.anomalies("MEMBER_BEFORE_JOINING").filter(row__row_number=27).exists()
        )

    def test_missing_currency_defaults_to_base(self):
        self.assert_flagged(28, "MISSING_CURRENCY")
        row = ImportRow.objects.get(batch=self.batch, row_number=28)
        self.assertEqual(row.parsed["currency"], "INR")

    def test_zero_amount_excluded(self):
        self.assert_flagged(31, "ZERO_AMOUNT")

    def test_day_month_swap_proposed(self):
        self.assert_flagged(34, "DATE_OUT_OF_SEQUENCE")
        a = self.anomalies("DATE_OUT_OF_SEQUENCE").get()
        self.assertEqual(a.proposed_action["date"], "2026-04-05")

    def test_meera_in_split_after_moving_out(self):
        self.assert_flagged(36, "MEMBER_AFTER_DEPARTURE")

    def test_farewell_dinner_before_departure_not_flagged(self):
        self.assertFalse(
            self.anomalies("MEMBER_AFTER_DEPARTURE").filter(row__row_number=33).exists()
        )

    def test_sam_deposit_is_personal_transfer(self):
        self.assert_flagged(38, "PERSONAL_TRANSFER")

    def test_redundant_split_details_on_equal(self):
        self.assert_flagged(42, "REDUNDANT_SPLIT_DETAILS")

    def test_at_least_12_problems_detected(self):
        codes = set(self.anomalies().values_list("code", flat=True))
        self.assertGreaterEqual(len(codes), 12, codes)

    def test_nothing_committed_while_staged(self):
        self.assertEqual(Expense.objects.count(), 0)
        self.assertEqual(Settlement.objects.count(), 0)


class AnnexCommitTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("aisha", password="passw0rd1")
        self.group = build_flat_group(self.user)
        self.batch = ImportBatch.objects.create(
            group=self.group,
            uploaded_by=self.user,
            file_name="expenses_export.csv",
            fx_rates={"USD": "83.00"},
        )
        with open(DATA, "rb") as f:
            pipeline.stage_batch(self.batch, pipeline.read_rows(f, "expenses_export.csv"))

    def approve_all(self):
        for a in ImportAnomaly.objects.filter(row__batch=self.batch, resolved_action__isnull=True):
            a.resolved_action = a.proposed_action
            a.save()

    def test_commit_blocked_until_reviews_resolved(self):
        with self.assertRaises(committer.CommitError) as ctx:
            committer.commit_batch(self.batch, self.user)
        self.assertTrue(any("needs a decision" in e for e in ctx.exception.errors))

    def test_commit_with_all_proposals_approved(self):
        self.approve_all()
        results = committer.commit_batch(self.batch, self.user)
        dispositions = [r["disposition"] for r in results]
        self.assertEqual(dispositions.count("expense"), 36)
        self.assertEqual(dispositions.count("settlement"), 1)
        # skipped: exact dup, thalassa dup, missing payer, zero amount, deposit
        self.assertEqual(dispositions.count("skipped"), 5)

        net = group_net_balances(self.group)
        self.assertEqual(sum(net.values()), 0)

        by_name = {m.name: net[m.id] for m in self.group.members.all()}
        # Sam by hand: paid 3100 + 1990 = 5090.00;
        # owes 775 (drinks) + 345 (electricity) + 497.50 (groceries)
        #      + 3000 (furniture) + 750 (maid) = 5367.50  ->  net -277.50
        self.assertEqual(by_name["Sam"], -27750)
        # Kabir by hand: parasailing 150 USD / 5 people = 30 USD @ 83 = 2490.00
        self.assertEqual(by_name["Kabir"], -249000)

        # Kabir was created as a guest member by the approved proposal.
        kabir = self.group.members.get(name="Kabir")
        self.assertTrue(kabir.is_guest)

        # The settlement row became a Settlement, not an Expense.
        s = Settlement.objects.get()
        self.assertEqual((s.payer.name, s.payee.name, s.amount_base_minor), ("Rohan", "Aisha", 500000))

    def test_reviewer_can_override_a_proposal(self):
        self.approve_all()
        # Meera actually attended the Apr-2 groceries run: keep her in.
        a = ImportAnomaly.objects.get(row__batch=self.batch, code="MEMBER_AFTER_DEPARTURE")
        a.resolved_action = {"action": "keep"}
        a.save()
        # And give the mystery cleaning-supplies row a payer instead of skipping.
        a2 = ImportAnomaly.objects.get(row__batch=self.batch, code="MISSING_PAYER")
        a2.resolved_action = {"action": "set_payer", "name": "Aisha"}
        a2.save()

        committer.commit_batch(self.batch, self.user)

        groceries = Expense.objects.get(source_row_number=36)
        self.assertIn("Meera", [s.member.name for s in groceries.splits.all()])
        supplies = Expense.objects.get(source_row_number=13)
        self.assertEqual(supplies.paid_by.name, "Aisha")
        self.assertEqual(sum(net == 0 for net in [sum(group_net_balances(self.group).values())]), 1)

    def test_report_lists_every_anomaly_and_action(self):
        self.approve_all()
        committer.commit_batch(self.batch, self.user)
        report = committer.build_report(self.batch)
        self.assertEqual(report["total_rows"], 42)
        self.assertGreaterEqual(report["total_anomalies"], 20)
        self.assertEqual(report["dispositions"]["expense"], 36)
        flat = [a for r in report["rows"] for a in r["anomalies"]]
        self.assertTrue(all(a["action_taken"] for a in flat))
