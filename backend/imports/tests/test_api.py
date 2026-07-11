"""Full user journey through the HTTP API."""
from datetime import date
from pathlib import Path

from rest_framework.test import APITestCase

DATA = Path(__file__).resolve().parents[3] / "data" / "expenses_export.csv"


class ImportFlowApiTests(APITestCase):
    def auth(self):
        r = self.client.post(
            "/api/auth/register/",
            {"username": "aisha", "password": "passw0rd1", "first_name": "Aisha"},
        )
        self.assertEqual(r.status_code, 201)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {r.data['token']}")

    def build_group(self):
        r = self.client.post("/api/groups/", {"name": "Flat 42", "base_currency": "INR"})
        self.assertEqual(r.status_code, 201)
        gid = r.data["id"]
        members = [
            {"name": "Aisha", "joined_on": "2026-02-01"},
            {"name": "Rohan", "joined_on": "2026-02-01"},
            {"name": "Priya", "joined_on": "2026-02-01"},
            {"name": "Meera", "joined_on": "2026-02-01", "left_on": "2026-03-31"},
            {"name": "Sam", "joined_on": "2026-04-08"},
            {"name": "Dev", "joined_on": "2026-02-08", "is_guest": True},
        ]
        for m in members:
            r = self.client.post(f"/api/groups/{gid}/members/", m)
            self.assertEqual(r.status_code, 201, r.data)
        return gid

    def test_full_import_journey(self):
        self.auth()
        gid = self.build_group()

        with open(DATA, "rb") as f:
            r = self.client.post(
                f"/api/groups/{gid}/imports/",
                {"file": f, "fx_rates": '{"USD": "83.00"}'},
                format="multipart",
            )
        self.assertEqual(r.status_code, 201, r.data)
        bid = r.data["id"]
        self.assertEqual(r.data["total_rows"], 42)
        self.assertGreater(r.data["review_open"], 0)

        # Commit is refused while reviews are open.
        r = self.client.post(f"/api/groups/{gid}/imports/{bid}/commit/")
        self.assertEqual(r.status_code, 400)

        # Override one proposal: assign the mystery payer.
        detail = self.client.get(f"/api/groups/{gid}/imports/{bid}/").data
        missing_payer = next(
            a
            for row in detail["rows"]
            for a in row["anomalies"]
            if a["code"] == "MISSING_PAYER"
        )
        r = self.client.post(
            f"/api/groups/{gid}/imports/{bid}/anomalies/{missing_payer['id']}/resolve/",
            {"action": "set_payer", "name": "Aisha"},
        )
        self.assertEqual(r.status_code, 200)

        # Approve everything else as proposed, then commit.
        r = self.client.post(f"/api/groups/{gid}/imports/{bid}/approve-all/")
        self.assertEqual(r.status_code, 200)
        r = self.client.post(f"/api/groups/{gid}/imports/{bid}/commit/")
        self.assertEqual(r.status_code, 200, r.data)

        # The overridden row became an expense paid by Aisha.
        r = self.client.get(f"/api/groups/{gid}/expenses/")
        supplies = next(e for e in r.data if e["source_row_number"] == 13)
        self.assertEqual(supplies["paid_by_name"], "Aisha")

        # Balances are consistent and the report is complete.
        balances = self.client.get(f"/api/groups/{gid}/balances/").data
        self.assertEqual(sum(b["net_minor"] for b in balances["balances"]), 0)
        self.assertTrue(balances["settle_up"])
        report = self.client.get(f"/api/groups/{gid}/imports/{bid}/report/").data
        self.assertEqual(report["status"], "committed")
        self.assertEqual(report["total_rows"], 42)

        # Rohan's drill-down: every entry sums to his net (no magic numbers).
        rohan = next(b for b in balances["balances"] if b["name"] == "Rohan")
        ledger = self.client.get(
            f"/api/groups/{gid}/members/{rohan['member_id']}/ledger/"
        ).data
        self.assertEqual(
            sum(e["effect_minor"] for e in ledger["entries"]), rohan["net_minor"]
        )

    def test_group_access_is_membership_gated(self):
        self.auth()
        gid = self.build_group()
        # A second user with no membership cannot see the group.
        r2 = self.client.post(
            "/api/auth/register/", {"username": "mallory", "password": "passw0rd1"}
        )
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {r2.data['token']}")
        r = self.client.get(f"/api/groups/{gid}/balances/")
        self.assertEqual(r.status_code, 403)
        r = self.client.get(f"/api/groups/{gid}/expenses/")
        self.assertEqual(r.status_code, 403)
