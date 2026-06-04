from mcp.server import Server
from mcp.server.stdio import stdio_server
import mcp.types as types
import asyncio
import json
import logging
import time
from collections import defaultdict
from dotenv import load_dotenv
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.tools.calendar import (
    handle_get_events,
    handle_create_event,
    handle_update_event,
    handle_delete_event,
    handle_set_reminder,
    handle_find_free_slot,
    handle_create_recurring_event,
)

from src.tools.context import (
    handle_get_session_context,
    handle_update_session_context,
)

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s'
)
logger = logging.getLogger("calendar-pa")

app = Server("calendar-pa")

tool_stats = defaultdict(lambda: {"calls": 0, "total_ms": 0, "errors": 0})


@app.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="get_events",
            description=(
                "Fetch events from Google Calendar. Supports single date, "
                "date range, or keyword search. Use this before scheduling "
                "anything to check what's already on the calendar."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "date": {
                        "type": "string",
                        "description": "Single date in YYYY-MM-DD format"
                    },
                    "date_from": {
                        "type": "string",
                        "description": "Start of date range in YYYY-MM-DD format"
                    },
                    "date_to": {
                        "type": "string",
                        "description": "End of date range in YYYY-MM-DD format"
                    },
                    "query": {
                        "type": "string",
                        "description": "Keyword search across event titles and descriptions"
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum number of events to return, defaults to 20"
                    }
                }
            }
        ),
        types.Tool(
            name="create_event",
            description=(
                "Create a new event on Google Calendar. Automatically checks "
                "for conflicts before creating. Use when the user wants to "
                "schedule, book, block time, or set up a meeting."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "Event title"
                    },
                    "start": {
                        "type": "string",
                        "description": "ISO 8601 start datetime e.g. 2026-05-28T10:00:00"
                    },
                    "duration_minutes": {
                        "type": "integer",
                        "description": "Duration in minutes, defaults to 60"
                    },
                    "description": {
                        "type": "string",
                        "description": "Event description or notes"
                    },
                    "location": {
                        "type": "string",
                        "description": "Event location"
                    },
                    "timezone": {
                        "type": "string",
                        "description": "Timezone e.g. Africa/Lagos, Europe/Amsterdam. Defaults to Africa/Lagos"
                    },
                    "reminder_minutes": {
                        "type": "integer",
                        "description": "Minutes before event to send reminder, defaults to 30"
                    }
                },
                "required": ["title", "start"]
            }
        ),
        types.Tool(
            name="update_event",
            description=(
                "Update an existing calendar event — reschedule, rename, "
                "change duration, or update description. Requires event_id. "
                "Use get_events first to find the event_id."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "event_id": {
                        "type": "string",
                        "description": "Google Calendar event ID"
                    },
                    "title": {"type": "string"},
                    "start": {
                        "type": "string",
                        "description": "New start datetime in ISO 8601 format"
                    },
                    "duration_minutes": {"type": "integer"},
                    "description":      {"type": "string"},
                    "location":         {"type": "string"},
                    "timezone":         {"type": "string"},
                    "reminder_minutes": {"type": "integer"}
                },
                "required": ["event_id"]
            }
        ),
        types.Tool(
            name="delete_event",
            description=(
                "Delete a calendar event. Always fetches event details first "
                "and requires explicit confirmation before deleting. "
                "Use get_events first to find the event_id."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "event_id": {
                        "type": "string",
                        "description": "Google Calendar event ID"
                    },
                    "confirm": {
                        "type": "boolean",
                        "description": "Must be true to actually delete. Omit for safety check first."
                    }
                },
                "required": ["event_id"]
            }
        ),
        types.Tool(
            name="set_reminder",
            description=(
                "Add or update a reminder on an existing event. "
                "Use get_events first to find the event_id."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "event_id": {
                        "type": "string",
                        "description": "Google Calendar event ID"
                    },
                    "reminder_minutes": {
                        "type": "integer",
                        "description": "Minutes before event to send reminder, defaults to 30"
                    },
                    "method": {
                        "type": "string",
                        "description": "popup or email, defaults to popup"
                    }
                },
                "required": ["event_id"]
            }
        ),
        types.Tool(
            name="find_free_slot",
            description=(
                "Find available time slots in the calendar for a given activity. "
                "Uses AI reasoning to suggest the 3 best times based on existing "
                "schedule, activity type, and productivity patterns. "
                "Use when the user asks to find time, schedule something without "
                "a specific time, or wants to know when they're free."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "duration_minutes": {
                        "type": "integer",
                        "description": "How long the slot needs to be in minutes, defaults to 60"
                    },
                    "date_from": {
                        "type": "string",
                        "description": "Start of search range in YYYY-MM-DD format, defaults to today"
                    },
                    "date_to": {
                        "type": "string",
                        "description": "End of search range in YYYY-MM-DD format, defaults to 7 days from today"
                    },
                    "activity": {
                        "type": "string",
                        "description": "What the slot is for e.g. 'deep work session', 'client call', 'gym'"
                    },
                    "preferences": {
                        "type": "string",
                        "description": "Any time preferences e.g. 'mornings only', 'avoid Mondays', 'after 2pm'"
                    }
                }
            }
        ),
        types.Tool(
            name="create_recurring_event",
            description=(
                "Create a recurring calendar event with complex recurrence rules. "
                "Understands natural language recurrence like 'every second Tuesday', "
                "'every weekday', 'first Monday of the month', 'every 2 weeks'. "
                "Use when the user wants to set up a repeating event or routine."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "Event title"
                    },
                    "start": {
                        "type": "string",
                        "description": "First occurrence datetime in ISO 8601 format"
                    },
                    "recurrence": {
                        "type": "string",
                        "description": "Natural language recurrence e.g. 'every Monday', 'every weekday', 'first Tuesday of the month', 'every 2 weeks on Thursday'"
                    },
                    "duration_minutes": {
                        "type": "integer",
                        "description": "Duration in minutes, defaults to 60"
                    },
                    "end_condition": {
                        "type": "string",
                        "description": "When to stop e.g. 'after 10 occurrences', 'until December 31 2026', leave empty for indefinite"
                    },
                    "description":      {"type": "string"},
                    "location":         {"type": "string"},
                    "timezone":         {"type": "string"},
                    "reminder_minutes": {"type": "integer"}
                },
                "required": ["title", "start", "recurrence"]
            }
        ),
        types.Tool(
            name="get_session_context",
            description=(
                "Load the current calendar PA session context including preferences, "
                "last actions, and pending tasks. "
                "ALWAYS call this first before doing anything in a calendar session."
            ),
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        types.Tool(
            name="update_session_context",
            description=(
                "Save the current session state after completing a task. "
                "Call this after creating, updating, or deleting events."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "last_action": {
                        "type": "string",
                        "description": "Description of the last action taken"
                    },
                    "last_event_created": {
                        "type": "string",
                        "description": "Title of the last event created"
                    },
                    "pending_tasks": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of pending tasks or follow-ups"
                    },
                    "notes": {
                        "type": "string",
                        "description": "Any notes to carry forward to the next session"
                    },
                    "preferences": {
                        "type": "object",
                        "description": "User preferences to persist"
                    }
                }
            }
        ),
    ]


@app.list_resources()
async def list_resources() -> list[types.Resource]:
    return [
        types.Resource(
            uri="calendar://today",
            name="Today's schedule",
            description=(
                "All events scheduled for today. "
                "Read this before scheduling anything to avoid conflicts."
            ),
            mimeType="application/json"
        ),
        types.Resource(
            uri="calendar://week",
            name="This week's schedule",
            description="All events scheduled for the current week.",
            mimeType="application/json"
        ),
        types.Resource(
            uri="system://tool-stats",
            name="Tool call statistics",
            description="Metrics for all tool calls — useful for debugging.",
            mimeType="application/json"
        ),
    ]


@app.read_resource()
async def read_resource(uri: str) -> str:
    from datetime import datetime, timezone, timedelta

    normalized = str(uri).rstrip("/")

    if normalized == "calendar://today":
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return await handle_get_events({"date": today})

    if normalized == "calendar://week":
        today     = datetime.now(timezone.utc)
        week_start = today.strftime("%Y-%m-%d")
        week_end   = (today + timedelta(days=7)).strftime("%Y-%m-%d")
        return await handle_get_events({"date_from": week_start, "date_to": week_end})

    if normalized == "system://tool-stats":
        return json.dumps(tool_stats)

    raise ValueError(f"Unknown resource: {uri}")


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    handlers = {
        "get_events":             handle_get_events,
        "create_event":           handle_create_event,
        "update_event":           handle_update_event,
        "delete_event":           handle_delete_event,
        "set_reminder":           handle_set_reminder,
        "find_free_slot":         handle_find_free_slot,
        "create_recurring_event": handle_create_recurring_event,
        "get_session_context":    handle_get_session_context,
        "update_session_context": handle_update_session_context,
    }

    handler = handlers.get(name)
    if not handler:
        return [types.TextContent(
            type="text",
            text=json.dumps({"error": f"Unknown tool: {name}"})
        )]

    start = time.time()
    try:
        logger.info(json.dumps({"tool": name, "status": "started"}))

        import inspect
        sig = inspect.signature(handler)
        if "ctx" in sig.parameters:
            ctx = app.request_context
            result = await handler(arguments, ctx=ctx)
        else:
            result = await handler(arguments)

        tool_stats[name]["calls"]    += 1
        tool_stats[name]["total_ms"] += (time.time() - start) * 1000
        logger.info(json.dumps({"tool": name, "status": "success"}))
        return result if isinstance(result, list) else [types.TextContent(type="text", text=result)]

    except Exception as e:
        tool_stats[name]["errors"] += 1
        error_msg = f"Tool '{name}' failed: {str(e)}"
        logger.error(json.dumps({"tool": name, "status": "error", "error": str(e)}))
        return [types.TextContent(
            type="text",
            text=json.dumps({"error": error_msg})
        )]


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options()
        )

if __name__ == "__main__":
    asyncio.run(main())