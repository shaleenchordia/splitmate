"""Faithful machine conversion of the provided XLSX export to CSV.

The assignment annex arrived as an .xlsx export. Values are written out
verbatim (no cleaning, no corrections) so the CSV matches the sheet
exactly. Dates are serialized as ISO (YYYY-MM-DD) exactly as stored in
the sheet's date cells. The importer also accepts the .xlsx directly.
"""
import csv
import datetime
import sys

import openpyxl


def cell_to_str(value):
    if value is None:
        return ""
    if isinstance(value, datetime.datetime):
        return value.date().isoformat()
    if isinstance(value, float) and value == int(value):
        return str(int(value))
    return str(value)


def main(src: str, dst: str) -> None:
    wb = openpyxl.load_workbook(src, data_only=True)
    ws = wb.worksheets[0]
    with open(dst, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        for row in ws.iter_rows(values_only=True):
            writer.writerow([cell_to_str(c) for c in row])


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
