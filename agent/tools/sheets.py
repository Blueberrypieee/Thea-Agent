"""
tools/sheets.py
───────────────
Responsibility : Google Sheets actions via Service Account.
                 No AI logic. Pure execution.

Dependencies:
    pip install gspread google-auth

Setup:
    1. Enable Google Sheets API + Google Drive API in Google Cloud Console
    2. Create Service Account → download JSON key
    3. Save to: credentials/sheets_service_account.json
    4. Share your Google Sheet with the service account email

Input contract (JSON string):
    read_sheet   → '{"spreadsheet_id": "...", "sheet": "Sheet1", "range": "A1:C10"}'
    write_sheet  → '{"spreadsheet_id": "...", "sheet": "Sheet1", "range": "A1", "values": [["v1","v2"]]}'
    append_sheet → '{"spreadsheet_id": "...", "sheet": "Sheet1", "values": [["v1","v2"]]}'
"""

import json
import logging

logger = logging.getLogger(__name__)


# ── Output helpers ──────────────────────────────────────────────────────────────

def _ok(data) -> str:
    return json.dumps({"status": "success", "data": data}, ensure_ascii=False)

def _err(message: str) -> str:
    return json.dumps({"status": "error", "message": message}, ensure_ascii=False)


# ── Safe input parser ───────────────────────────────────────────────────────────

def _parse_input(raw: str) -> dict | None:
    """
    Parse JSON input safely.
    Returns None if input is not valid JSON — sheets tools REQUIRE structured input,
    so we return a clear error instead of guessing.
    """
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("sheets: non-JSON input received: %s", raw[:100])
        return None


# ── Sheets client ───────────────────────────────────────────────────────────────

def _get_client():
    """Lazy-load gspread client. Raises RuntimeError if deps missing."""
    try:
        import gspread
        from google.oauth2.service_account import Credentials
        from agent import config

        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]
        creds = Credentials.from_service_account_file(
            config.SHEETS_CREDENTIALS_PATH, scopes=scopes
        )
        return gspread.authorize(creds)

    except ImportError:
        raise RuntimeError("Missing dependencies. Run: pip install gspread google-auth")


# ── Tool functions ──────────────────────────────────────────────────────────────

def read_sheet(input: str) -> str:
    """
    Read data from a Google Sheet.

    Input JSON:
        {
            "spreadsheet_id": "1BxiM...",
            "sheet":          "Sheet1",   ← optional, default Sheet1
            "range":          "A1:C10"    ← optional, default all data
        }

    Returns structured JSON array — easier for LLM to reason about.
    """
    logger.info("read_sheet: starting")

    params = _parse_input(input)
    if params is None:
        return _err("Invalid JSON input. Required: {spreadsheet_id, sheet?, range?}")

    spreadsheet_id = params.get("spreadsheet_id")
    if not spreadsheet_id:
        return _err("Missing required field: spreadsheet_id")

    sheet_name = params.get("sheet", "Sheet1")
    range_     = params.get("range", "")

    try:
        client      = _get_client()
        spreadsheet = client.open_by_key(spreadsheet_id)
        worksheet   = spreadsheet.worksheet(sheet_name)

        data = worksheet.get(range_) if range_ else worksheet.get_all_values()

        if not data:
            return _ok([])

        logger.info("read_sheet: success | rows=%d | sheet=%s", len(data), sheet_name)
        # Return as 2D array — structured, LLM-friendly, no tab characters
        return _ok(data)

    except Exception as e:
        logger.error("read_sheet: failed | %s", e)
        return _err(str(e))


def write_sheet(input: str) -> str:
    """
    Write/overwrite values to a specific range in a Google Sheet.

    Input JSON:
        {
            "spreadsheet_id": "1BxiM...",
            "sheet":          "Sheet1",
            "range":          "A1",
            "values":         [["Name", "Score"], ["Alice", "95"]]
        }
    """
    logger.info("write_sheet: starting")

    params = _parse_input(input)
    if params is None:
        return _err("Invalid JSON input. Required: {spreadsheet_id, range, values, sheet?}")

    missing = [f for f in ("spreadsheet_id", "range", "values") if not params.get(f)]
    if missing:
        return _err(f"Missing required fields: {', '.join(missing)}")

    spreadsheet_id = params["spreadsheet_id"]
    sheet_name     = params.get("sheet", "Sheet1")
    range_         = params["range"]
    values         = params["values"]

    try:
        client      = _get_client()
        spreadsheet = client.open_by_key(spreadsheet_id)
        worksheet   = spreadsheet.worksheet(sheet_name)

        worksheet.update(range_, values)
        logger.info("write_sheet: success | rows=%d | sheet=%s", len(values), sheet_name)
        return _ok(f"Written {len(values)} row(s) to {sheet_name}!{range_}")

    except Exception as e:
        logger.error("write_sheet: failed | %s", e)
        return _err(str(e))


def append_sheet(input: str) -> str:
    """
    Append rows to the bottom of a Google Sheet.

    Input JSON:
        {
            "spreadsheet_id": "1BxiM...",
            "sheet":          "Sheet1",
            "values":         [["Alice", "95"], ["Bob", "88"]]
        }
    """
    logger.info("append_sheet: starting")

    params = _parse_input(input)
    if params is None:
        return _err("Invalid JSON input. Required: {spreadsheet_id, values, sheet?}")

    missing = [f for f in ("spreadsheet_id", "values") if not params.get(f)]
    if missing:
        return _err(f"Missing required fields: {', '.join(missing)}")

    spreadsheet_id = params["spreadsheet_id"]
    sheet_name     = params.get("sheet", "Sheet1")
    values         = params["values"]

    try:
        client      = _get_client()
        spreadsheet = client.open_by_key(spreadsheet_id)
        worksheet   = spreadsheet.worksheet(sheet_name)

        worksheet.append_rows(values)
        logger.info("append_sheet: success | rows=%d | sheet=%s", len(values), sheet_name)
        return _ok(f"Appended {len(values)} row(s) to {sheet_name}")

    except Exception as e:
        logger.error("append_sheet: failed | %s", e)
        return _err(str(e))


# ── Registry fragment ───────────────────────────────────────────────────────────

TOOLS = {
    "read_sheet": {
        "fn":          read_sheet,
        "description": (
            "Read data from a Google Sheet. "
            'Input JSON: {"spreadsheet_id": "...", "sheet": "Sheet1", "range": "A1:C10"}'
        ),
    },
    "write_sheet": {
        "fn":          write_sheet,
        "description": (
            "Write/overwrite data to a Google Sheet range. "
            'Input JSON: {"spreadsheet_id": "...", "sheet": "Sheet1", "range": "A1", "values": [["col1","col2"]]}'
        ),
    },
    "append_sheet": {
        "fn":          append_sheet,
        "description": (
            "Append rows to the bottom of a Google Sheet. "
            'Input JSON: {"spreadsheet_id": "...", "sheet": "Sheet1", "values": [["val1","val2"]]}'
        ),
    },
}

