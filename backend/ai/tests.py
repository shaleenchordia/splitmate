"""Tests for the offline AI fallbacks (the Gemini path is exercised
manually — these guarantee the app is fully usable without a key)."""
from datetime import date

from django.test import SimpleTestCase

from .local import build_import_briefing, categorize, parse_expense_text

MEMBERS = ["Aisha", "Rohan", "Priya", "Sam"]
TODAY = date(2026, 7, 12)


class ParseExpenseTextTests(SimpleTestCase):
    def parse(self, text):
        return parse_expense_text(text, MEMBERS, "INR", today=TODAY)

    def test_basic_line(self):
        r = self.parse("Dinner at Truffles 1200 paid by Aisha split with Rohan and Priya")
        e = r["expense"]
        self.assertEqual(e["amount"], 1200)
        self.assertEqual(e["currency"], "INR")
        self.assertEqual(e["paid_by"], "Aisha")
        self.assertEqual(e["split_type"], "equal")
        # payer is included in the split alongside the named people
        self.assertEqual(
            sorted(p["name"] for p in e["participants"]), ["Aisha", "Priya", "Rohan"]
        )
        self.assertIn("Dinner at Truffles", e["description"])

    def test_currency_symbol_and_date_word(self):
        r = self.parse("Uber $25 yesterday, Sam paid")
        e = r["expense"]
        self.assertEqual(e["currency"], "USD")
        self.assertEqual(e["amount"], 25)
        self.assertEqual(e["date"], "2026-07-11")
        self.assertEqual(e["paid_by"], "Sam")

    def test_defaults_to_everyone(self):
        r = self.parse("Wifi bill 850")
        names = [p["name"] for p in r["expense"]["participants"]]
        self.assertEqual(names, MEMBERS)

    def test_percentage_split(self):
        r = self.parse("Groceries 900, Aisha 60% and Rohan 40%")
        e = r["expense"]
        self.assertEqual(e["split_type"], "percentage")
        self.assertEqual(
            {(p["name"], p["percent"]) for p in e["participants"]},
            {("Aisha", 60.0), ("Rohan", 40.0)},
        )

    def test_share_split(self):
        r = self.parse("Rent 30000 Rohan 2 shares Priya 1 share")
        e = r["expense"]
        self.assertEqual(e["split_type"], "share")
        self.assertEqual(
            {(p["name"], p["units"]) for p in e["participants"]},
            {("Rohan", 2), ("Priya", 1)},
        )

    def test_unknown_member_warns(self):
        r = self.parse("Snacks 100 split with Vikram")
        self.assertTrue(any("Vikram" in w for w in r["warnings"]))

    def test_missing_amount_warns(self):
        r = self.parse("Dinner with Rohan")
        self.assertIsNone(r["expense"]["amount"])
        self.assertTrue(any("amount" in w.lower() for w in r["warnings"]))

    def test_explicit_date(self):
        r = self.parse("Cab 300 on 5/3")
        self.assertEqual(r["expense"]["date"], "2026-03-05")


class CategorizeTests(SimpleTestCase):
    def test_categories(self):
        self.assertEqual(categorize("Dinner at Truffles"), "Food & dining")
        self.assertEqual(categorize("Electricity bill April"), "Utilities")
        self.assertEqual(categorize("Uber to airport"), "Travel & transport")
        self.assertEqual(categorize("May rent"), "Rent & deposit")
        self.assertEqual(categorize("Mystery"), "Other")


class ImportBriefingTests(SimpleTestCase):
    def test_briefing_counts_and_recommends(self):
        summary = {"total_rows": 10}
        anomalies = [
            {"id": 1, "code": "AMBIGUOUS_DATE"},
            {"id": 2, "code": "AMBIGUOUS_DATE"},
            {"id": 3, "code": "DUPLICATE_SUSPECT"},
        ]
        out = build_import_briefing(summary, anomalies)
        self.assertIn("3 decisions", out["briefing"])
        self.assertEqual(len(out["recommendations"]), 3)
        self.assertEqual({r["anomaly_id"] for r in out["recommendations"]}, {1, 2, 3})

    def test_all_clear(self):
        out = build_import_briefing({"total_rows": 5}, [])
        self.assertIn("committed", out["briefing"])
