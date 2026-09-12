#!/usr/bin/env python3
"""
probe_drive.py — feasibility probe for the proposed CCC traffic-count ETL.

Read-only. This is NOT part of the deployed pipeline; it's a one-off risk
assessment. It reads the PUBLIC CCC intersection-counts Google Drive folder via
the Drive REST API (API key from $DRIVE_API_KEY or --key), walks each year
subfolder, downloads ONE workbook per folder, and runs the existing
``traffic_counts_parser.parse_xlsx`` on it. It prints a folder -> rows-parsed
table so we can see which workbook formats the current parser already handles and
where formats have drifted (e.g. the 2026 "Turning Count Template" workbooks that
parse to 0 rows).

Uses only the standard library for Drive access (no google-api-python-client) so
it runs anywhere. It does need openpyxl at import time (the parser uses it), so
run it from the project venv:

    export DRIVE_API_KEY=your_key          # never commit the key
    python scripts/probe_drive.py          # defaults to the CCC top folder
    python scripts/probe_drive.py --keep   # keep the downloaded workbooks

The API key is read from the environment and never written anywhere.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

# Make the sibling pipeline modules importable (traffic_counts_parser, _sim_root).
SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

DRIVE_API = "https://www.googleapis.com/drive/v3/files"
# CCC intersection traffic-counts folder (public), per traffic_counts_parser.py's help.
TOP_FOLDER_ID = "1oP5gcuKR1bHB9Xn2B4ILZZd_LhpMggxU"
FOLDER_MIME = "application/vnd.google-apps.folder"
GOOGLE_SHEET_MIME = "application/vnd.google-apps.spreadsheet"
EXCEL_EXTS = (".xlsx", ".xlsm", ".xls", ".xltx", ".xltm")


def _get(url: str, timeout: int = 60):
    """GET a URL, surfacing the Drive error body on failure (e.g. 403/400)."""
    try:
        return urllib.request.urlopen(url, timeout=timeout)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:400]
        raise SystemExit(f"Drive API error {e.code}: {body}") from e


def _api(params: dict, key: str) -> dict:
    q = dict(params)
    q["key"] = key
    q.setdefault("supportsAllDrives", "true")
    q.setdefault("includeItemsFromAllDrives", "true")
    with _get(DRIVE_API + "?" + urllib.parse.urlencode(q)) as r:
        return json.load(r)


def list_children(folder_id: str, key: str) -> list[dict]:
    """Every child of a folder, following pagination."""
    out: list[dict] = []
    token = None
    while True:
        params = {
            "q": f"'{folder_id}' in parents and trashed=false",
            "fields": "nextPageToken,files(id,name,mimeType,size,modifiedTime)",
            "pageSize": "1000",
            "orderBy": "name",
        }
        if token:
            params["pageToken"] = token
        data = _api(params, key)
        out.extend(data.get("files", []))
        token = data.get("nextPageToken")
        if not token:
            return out


def find_one_workbook(folder_id: str, key: str, depth: int = 0, max_depth: int = 3):
    """First Excel workbook in a folder, descending into subfolders if needed."""
    children = list_children(folder_id, key)
    for f in children:
        if f["name"].lower().endswith(EXCEL_EXTS):
            return f
    for f in children:  # note a native Google Sheet only if no real workbook here
        if f["mimeType"] == GOOGLE_SHEET_MIME:
            return f
    if depth < max_depth:
        for f in children:
            if f["mimeType"] == FOLDER_MIME:
                found = find_one_workbook(f["id"], key, depth + 1, max_depth)
                if found:
                    return found
    return None


def download(file_id: str, key: str, dest: Path) -> None:
    url = DRIVE_API + "/" + urllib.parse.quote(file_id) + "?" + urllib.parse.urlencode(
        {"alt": "media", "key": key, "supportsAllDrives": "true"}
    )
    with _get(url, timeout=180) as r, open(dest, "wb") as fh:
        fh.write(r.read())


def main() -> int:
    ap = argparse.ArgumentParser(description="Probe CCC Drive folder + parser coverage.")
    ap.add_argument("--folder", default=TOP_FOLDER_ID, help="Top folder id (default: CCC counts).")
    ap.add_argument(
        "--key",
        default=os.environ.get("DRIVE_API_KEY") or os.environ.get("KEY"),
        help="Drive API key (or set $DRIVE_API_KEY / $KEY).",
    )
    ap.add_argument("--keep", action="store_true", help="Keep the downloaded workbooks.")
    args = ap.parse_args()

    if not args.key:
        print("ERROR: no API key. Set $DRIVE_API_KEY or pass --key.", file=sys.stderr)
        return 2

    try:
        from traffic_counts_parser import parse_xlsx
    except Exception as e:  # noqa: BLE001 - want the reason surfaced to the user
        print(f"ERROR importing parser: {e}\nRun from the project venv (needs openpyxl).", file=sys.stderr)
        return 2

    print(f"Listing top folder {args.folder} ...")
    top = list_children(args.folder, args.key)
    folders = [f for f in top if f["mimeType"] == FOLDER_MIME]
    if not folders:
        print("No subfolders found — is the folder public and the key valid?", file=sys.stderr)
        return 1

    tmp = Path(tempfile.mkdtemp(prefix="drive_probe_"))
    print(f"One workbook per folder → {tmp}\n")

    fmt = "{:<22} {:<42} {:>7}  {}"
    print(fmt.format("FOLDER", "WORKBOOK", "ROWS", "NOTE"))
    print("-" * 92)

    results: list[tuple[str, int | None]] = []
    for folder in folders:
        wb = find_one_workbook(folder["id"], args.key)
        name = folder["name"][:22]
        if wb is None:
            print(fmt.format(name, "(no workbook found)", "-", ""))
            results.append((folder["name"], None))
            continue
        if wb["mimeType"] == GOOGLE_SHEET_MIME:
            print(fmt.format(name, wb["name"][:42], "-", "native Google Sheet (needs export)"))
            results.append((folder["name"], None))
            continue
        dest = tmp / (folder["name"] + "__" + wb["name"]).replace("/", "_")
        try:
            download(wb["id"], args.key, dest)
            rows = parse_xlsx(dest)
            n = len(rows)
            print(fmt.format(name, wb["name"][:42], n, "OK" if n else "parsed 0 rows"))
            results.append((folder["name"], n))
        except SystemExit:
            raise
        except Exception as e:  # noqa: BLE001 - parser raises ValueError on layout mismatch
            msg = str(e).splitlines()[0][:48]
            print(fmt.format(name, wb["name"][:42], "ERR", msg))
            results.append((folder["name"], None))

    ok = [r for r in results if isinstance(r[1], int) and r[1] > 0]
    print("\nSUMMARY")
    print(f"  folders probed:        {len(results)}")
    print(f"  parsed OK (>0 rows):   {len(ok)}")
    print(f"  parsed 0 rows / error: {len(results) - len(ok)}")
    if not ok:
        print("  → parser handled NONE of the probed workbooks — these formats need parser work.")
    elif len(ok) < len(results):
        print("  → parser handles SOME formats but not all — format drift confirmed.")
        print("    Budget parser-extension work for the folders that failed above.")
    else:
        print("  → parser handled every probed workbook — low format-drift risk.")

    if args.keep:
        print(f"\nWorkbooks kept in {tmp}")
    else:
        import shutil

        shutil.rmtree(tmp, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
