import json
import os
from pathlib import Path
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

CONTEXT_FILE = Path(os.getenv(
    "CONTEXT_FILE",
    str(Path(__file__).parent.parent.parent / "data" / "session_context.json")
))


def _ensure_data_dir():
    CONTEXT_FILE.parent.mkdir(parents=True, exist_ok=True)


async def handle_get_session_context(args: dict) -> str:
    """
    Load the current session context.
    ALWAYS call this first at the start of any calendar PA session.
    """
    _ensure_data_dir()

    if not CONTEXT_FILE.exists():
        # first time — return empty context
        default = {
            "last_action":     None,
            "last_event_created": None,
            "pending_tasks":   [],
            "preferences": {
                "timezone":        "Africa/Lagos",
                "work_hours_start": "09:00",
                "work_hours_end":   "18:00",
                "reminder_default": 30
            },
            "notes": "",
            "last_updated": None
        }
        return json.dumps({"context": default, "is_new": True})

    try:
        context = json.loads(CONTEXT_FILE.read_text())
        return json.dumps({"context": context, "is_new": False})
    except Exception as e:
        return json.dumps({"error": f"Failed to load context: {str(e)}"})


async def handle_update_session_context(args: dict) -> str:
    """
    Save the current session state for continuity across sessions.
    Call this after completing any significant action.
    """
    _ensure_data_dir()

    # load existing context first
    existing = {}
    if CONTEXT_FILE.exists():
        try:
            existing = json.loads(CONTEXT_FILE.read_text())
        except Exception:
            pass

    # merge updates
    updates = {k: v for k, v in args.items()}
    updates["last_updated"] = datetime.now(timezone.utc).isoformat()

    existing.update(updates)

    CONTEXT_FILE.write_text(json.dumps(existing, indent=2))

    return json.dumps({
        "success": True,
        "message": "Session context updated.",
        "context": existing
    })