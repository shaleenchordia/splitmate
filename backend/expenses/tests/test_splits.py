from decimal import Decimal

from django.test import SimpleTestCase

from expenses.services.splits import SplitError, compute_splits


class EqualSplitTests(SimpleTestCase):
    def test_divides_evenly(self):
        shares = compute_splits(
            "equal", 1200, [{"member_id": 1}, {"member_id": 2}, {"member_id": 3}]
        )
        self.assertEqual(shares, {1: 400, 2: 400, 3: 400})

    def test_remainder_goes_to_first_participants(self):
        # 1000 paise across 3 people: 334, 333, 333 — never 999 or 1001.
        shares = compute_splits(
            "equal", 1000, [{"member_id": 1}, {"member_id": 2}, {"member_id": 3}]
        )
        self.assertEqual(sum(shares.values()), 1000)
        self.assertEqual(sorted(shares.values(), reverse=True), [334, 333, 333])
        self.assertEqual(shares[1], 334)  # deterministic: input order breaks ties

    def test_negative_total_is_a_refund(self):
        shares = compute_splits(
            "equal", -3000, [{"member_id": 1}, {"member_id": 2}, {"member_id": 3}, {"member_id": 4}]
        )
        self.assertEqual(sum(shares.values()), -3000)
        self.assertTrue(all(s < 0 for s in shares.values()))

    def test_duplicate_participant_rejected(self):
        with self.assertRaises(SplitError):
            compute_splits("equal", 100, [{"member_id": 1}, {"member_id": 1}])


class PercentageSplitTests(SimpleTestCase):
    def test_exact_percents(self):
        shares = compute_splits(
            "percentage",
            144000,
            [
                {"member_id": 1, "percent": Decimal("30")},
                {"member_id": 2, "percent": Decimal("30")},
                {"member_id": 3, "percent": Decimal("30")},
                {"member_id": 4, "percent": Decimal("10")},
            ],
        )
        self.assertEqual(shares, {1: 43200, 2: 43200, 3: 43200, 4: 14400})

    def test_bad_sum_rejected(self):
        with self.assertRaises(SplitError):
            compute_splits(
                "percentage",
                1000,
                [
                    {"member_id": 1, "percent": Decimal("30")},
                    {"member_id": 2, "percent": Decimal("80")},
                ],
            )

    def test_normalized_percents_within_tolerance(self):
        # 110% normalized proportionally quantizes to 4dp and sums to 99.9999;
        # allocation stays exact to the paisa.
        shares = compute_splits(
            "percentage",
            144000,
            [
                {"member_id": 1, "percent": Decimal("27.2727")},
                {"member_id": 2, "percent": Decimal("27.2727")},
                {"member_id": 3, "percent": Decimal("27.2727")},
                {"member_id": 4, "percent": Decimal("18.1818")},
            ],
        )
        self.assertEqual(sum(shares.values()), 144000)
        # 30/110 of 1440.00 = 392.73 (well, 392.727... -> largest remainder)
        self.assertEqual(shares[4], 26182)  # 20/110 * 144000 = 26181.81...

    def test_never_loses_a_paisa(self):
        shares = compute_splits(
            "percentage",
            99999,
            [
                {"member_id": 1, "percent": Decimal("33.33")},
                {"member_id": 2, "percent": Decimal("33.33")},
                {"member_id": 3, "percent": Decimal("33.34")},
            ],
        )
        self.assertEqual(sum(shares.values()), 99999)


class ShareSplitTests(SimpleTestCase):
    def test_weighted_units(self):
        # Scooter rentals: 3600.00 with units Aisha 1, Rohan 2, Priya 1, Dev 2.
        shares = compute_splits(
            "share",
            360000,
            [
                {"member_id": 1, "units": 1},
                {"member_id": 2, "units": 2},
                {"member_id": 3, "units": 1},
                {"member_id": 4, "units": 2},
            ],
        )
        self.assertEqual(shares, {1: 60000, 2: 120000, 3: 60000, 4: 120000})

    def test_indivisible_units(self):
        shares = compute_splits(
            "share", 100, [{"member_id": 1, "units": 1}, {"member_id": 2, "units": 2}]
        )
        self.assertEqual(sum(shares.values()), 100)
        self.assertEqual(shares[2], 67)  # 66.67 rounds up via largest remainder


class UnequalSplitTests(SimpleTestCase):
    def test_exact_amounts(self):
        shares = compute_splits(
            "unequal",
            150000,
            [
                {"member_id": 1, "amount_minor": 70000},
                {"member_id": 2, "amount_minor": 40000},
                {"member_id": 3, "amount_minor": 40000},
            ],
        )
        self.assertEqual(shares, {1: 70000, 2: 40000, 3: 40000})

    def test_sum_mismatch_rejected(self):
        with self.assertRaises(SplitError):
            compute_splits(
                "unequal",
                150000,
                [
                    {"member_id": 1, "amount_minor": 70000},
                    {"member_id": 2, "amount_minor": 40000},
                ],
            )
