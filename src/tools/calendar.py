import json
from datetime import datetime, timezone, timedelta
from src.auth import get_calendar_service
from dotenv import load_dotenv
import os

load_dotenv()

CALENDAR_ID = os.getenv("CALENDAR_ID", "primary")


def _format_event(event: dict) -> dict:
    """Normalize a raw Google Calendar event into a clean dict."""
    start = event.get("start", {})
    end   = event.get("end", {})

    return {
        "id":          event.get("id"),
        "title":       event.get("summary", "Untitled"),
        "start":       start.get("dateTime", start.get("date")),
        "end":         end.get("dateTime",   end.get("date")),
        "description": event.get("description", ""),
        "location":    event.get("location", ""),
        "recurring":   "recurringEventId" in event,
        "reminders":   event.get("reminders", {}),
    }


async def handle_get_events(args: dict) -> str:
    """
    Fetch events from Google Calendar.
    Supports: single date, date range, or keyword search.
    """
    date       = args.get("date")
    date_from  = args.get("date_from")
    date_to    = args.get("date_to")
    query      = args.get("query")
    max_results = args.get("max_results", 20)

    svc = get_calendar_service()

    # build time bounds
    if date:
        # single day
        time_min = f"{date}T00:00:00Z"
        time_max = f"{date}T23:59:59Z"
    elif date_from and date_to:
        # date range
        time_min = f"{date_from}T00:00:00Z"
        time_max = f"{date_to}T23:59:59Z"
    else:
        # default to today
        today    = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        time_min = f"{today}T00:00:00Z"
        time_max = f"{today}T23:59:59Z"

    params = {
        "calendarId":   CALENDAR_ID,
        "timeMin":      time_min,
        "timeMax":      time_max,
        "maxResults":   max_results,
        "singleEvents": True,
        "orderBy":      "startTime",
    }

    # add keyword search if provided
    if query:
        params["q"] = query

    result = svc.events().list(**params).execute()
    events = [_format_event(e) for e in result.get("items", [])]

    if not events:
        return json.dumps({"message": "No events found.", "events": []})

    return json.dumps({"count": len(events), "events": events}, default=str)


async def handle_create_event(args: dict) -> str:
    """
    Create a new event on Google Calendar.
    Checks for conflicts before creating.
    """
    title       = args["title"]
    start       = args["start"]
    duration    = args.get("duration_minutes", 60)
    description = args.get("description", "")
    location    = args.get("location", "")
    timezone    = args.get("timezone", "Africa/Lagos")

    # parse start time
    try:
        start_dt = datetime.fromisoformat(start)
    except ValueError:
        return json.dumps({"error": f"Invalid start time format: {start}. Use ISO 8601 e.g. 2026-05-28T10:00:00"})

    # calculate end time
    from datetime import timedelta
    end_dt = start_dt + timedelta(minutes=duration)

    # --- conflict detection ---
    svc = get_calendar_service()

    conflict_check = svc.events().list(
        calendarId=CALENDAR_ID,
        timeMin=start_dt.isoformat() + "Z" if start_dt.tzinfo is None else start_dt.isoformat(),
        timeMax=end_dt.isoformat() + "Z" if end_dt.tzinfo is None else end_dt.isoformat(),
        singleEvents=True,
        orderBy="startTime"
    ).execute()

    conflicts = conflict_check.get("items", [])
    if conflicts:
        conflict_titles = [e.get("summary", "Untitled") for e in conflicts]
        return json.dumps({
            "error":     "conflict_detected",
            "message":   f"This time slot conflicts with: {', '.join(conflict_titles)}. Please choose a different time.",
            "conflicts": [_format_event(e) for e in conflicts]
        })

    # --- no conflicts, create the event ---
    event_body = {
        "summary":     title,
        "description": description,
        "location":    location,
        "start": {
            "dateTime": start_dt.isoformat(),
            "timeZone": timezone
        },
        "end": {
            "dateTime": end_dt.isoformat(),
            "timeZone": timezone
        },
        "reminders": {
            "useDefault": False,
            "overrides": [
                {"method": "popup", "minutes": args.get("reminder_minutes", 30)}
            ]
        }
    }

    created = svc.events().insert(
        calendarId=CALENDAR_ID,
        body=event_body
    ).execute()

    return json.dumps({
        "success": True,
        "message": f"Event '{title}' created successfully.",
        "event":   _format_event(created)
    }, default=str)


async def handle_update_event(args: dict) -> str:
    event_id = args.get("event_id")
    if not event_id:
        return json.dumps({"error": "event_id is required."})

    svc = get_calendar_service()

    try:
        event = svc.events().get(
            calendarId=CALENDAR_ID,
            eventId=event_id
        ).execute()
    except Exception as e:
        return json.dumps({"error": f"Event not found: {str(e)}"})

    if "title" in args:
        event["summary"] = args["title"]
    if "description" in args:
        event["description"] = args["description"]
    if "location" in args:
        event["location"] = args["location"]

    if "start" in args:
        from datetime import timedelta
        try:
            start_dt = datetime.fromisoformat(args["start"])
        except ValueError:
            return json.dumps({"error": f"Invalid start time: {args['start']}. Use ISO 8601."})

        duration = args.get("duration_minutes", 60)
        end_dt   = start_dt + timedelta(minutes=duration)
        tz       = args.get("timezone", "Africa/Lagos")

        conflict_check = svc.events().list(
            calendarId=CALENDAR_ID,
            timeMin=start_dt.isoformat() + "Z" if start_dt.tzinfo is None else start_dt.isoformat(),
            timeMax=end_dt.isoformat() + "Z" if end_dt.tzinfo is None else end_dt.isoformat(),
            singleEvents=True,
            orderBy="startTime"
        ).execute()

        conflicts = [
            e for e in conflict_check.get("items", [])
            if e["id"] != event_id
        ]

        if conflicts:
            conflict_titles = [e.get("summary", "Untitled") for e in conflicts]
            return json.dumps({
                "error":     "conflict_detected",
                "message":   f"New time conflicts with: {', '.join(conflict_titles)}.",
                "conflicts": [_format_event(e) for e in conflicts]
            })

        event["start"] = {"dateTime": start_dt.isoformat(), "timeZone": tz}
        event["end"]   = {"dateTime": end_dt.isoformat(),   "timeZone": tz}

    if "reminder_minutes" in args:
        event["reminders"] = {
            "useDefault": False,
            "overrides": [{"method": "popup", "minutes": args["reminder_minutes"]}]
        }

    try:
        updated = svc.events().update(
            calendarId=CALENDAR_ID,
            eventId=event_id,
            body=event
        ).execute()
        return json.dumps({
            "success": True,
            "message": "Event updated successfully.",
            "event":   _format_event(updated)
        }, default=str)
    except Exception as e:
        return json.dumps({"error": f"Failed to update event: {str(e)}"})


async def handle_delete_event(args: dict) -> str:
    """
    Delete an event. Requires event_id and explicit confirmation.
    """
    event_id = args.get("event_id")
    confirm  = args.get("confirm", False)

    if not event_id:
        return json.dumps({"error": "event_id is required."})

    if not confirm:
        # fetch event details first so Claude can show the user what's being deleted
        svc = get_calendar_service()
        try:
            event = svc.events().get(
                calendarId=CALENDAR_ID,
                eventId=event_id
            ).execute()
            return json.dumps({
                "confirmation_required": True,
                "message": f"Are you sure you want to delete '{event.get('summary', 'Untitled')}'? Call delete_event again with confirm=true to proceed.",
                "event": _format_event(event)
            }, default=str)
        except Exception as e:
            return json.dumps({"error": f"Event not found: {str(e)}"})

    # confirmed — delete
    svc = get_calendar_service()
    try:
        svc.events().delete(
            calendarId=CALENDAR_ID,
            eventId=event_id
        ).execute()
        return json.dumps({
            "success": True,
            "message": f"Event deleted successfully."
        })
    except Exception as e:
        return json.dumps({"error": f"Failed to delete event: {str(e)}"})
    

async def handle_set_reminder(args: dict) -> str:
    event_id         = args.get("event_id")
    reminder_minutes = args.get("reminder_minutes", 30)
    method           = args.get("method", "popup")

    if not event_id:
        return json.dumps({"error": "event_id is required."})

    if method not in ("popup", "email"):
        return json.dumps({"error": "method must be 'popup' or 'email'."})

    if not isinstance(reminder_minutes, int) or reminder_minutes < 0:
        return json.dumps({"error": "reminder_minutes must be a positive integer."})

    svc = get_calendar_service()
    try:
        event = svc.events().get(
            calendarId=CALENDAR_ID,
            eventId=event_id
        ).execute()
    except Exception as e:
        return json.dumps({"error": f"Event not found: {str(e)}"})

    event["reminders"] = {
        "useDefault": False,
        "overrides": [{"method": method, "minutes": reminder_minutes}]
    }

    try:
        updated = svc.events().update(
            calendarId=CALENDAR_ID,
            eventId=event_id,
            body=event
        ).execute()
        return json.dumps({
            "success": True,
            "message": f"Reminder set — {reminder_minutes} minutes before via {method}.",
            "event":   _format_event(updated)
        }, default=str)
    except Exception as e:
        return json.dumps({"error": f"Failed to update reminder: {str(e)}"})


async def handle_find_free_slot(args: dict, ctx=None) -> str:
    """
    Find free time slots in the calendar.
    Uses sampling to reason about the best slot for the given activity.
    """
    duration     = args.get("duration_minutes", 60)
    date_from    = args.get("date_from")
    date_to      = args.get("date_to")
    activity     = args.get("activity", "a meeting")
    preferences  = args.get("preferences", "")

    if not date_from or not date_to:
        # default to next 7 days
        from datetime import timezone, timedelta
        today     = datetime.now(timezone.utc)
        date_from = today.strftime("%Y-%m-%d")
        date_to   = (today + timedelta(days=7)).strftime("%Y-%m-%d")

    # fetch all events in the range
    events_json = await handle_get_events({
        "date_from": date_from,
        "date_to":   date_to,
        "max_results": 50
    })
    events_data = json.loads(events_json)
    events      = events_data.get("events", [])

    # build a readable schedule summary for Claude to reason about
    if events:
        schedule_summary = "\n".join([
            f"- {e['title']}: {e['start']} to {e['end']}"
            for e in events
        ])
    else:
        schedule_summary = "No events scheduled in this period."

    # use sampling if context is available
    if ctx:
        try:
            from mcp.types import (
                CreateMessageRequestParams,
                SamplingMessage,
                TextContent as SamplingTextContent
            )

            sampling_prompt = (
                f"I need to find a free {duration}-minute slot for: {activity}\n"
                f"Date range: {date_from} to {date_to}\n"
                f"User preferences: {preferences if preferences else 'none specified'}\n\n"
                f"Current schedule:\n{schedule_summary}\n\n"
                f"Please suggest the 3 best available time slots considering:\n"
                f"1. The existing events above (avoid conflicts)\n"
                f"2. Typical productive hours (9am-6pm preferred)\n"
                f"3. The nature of the activity: {activity}\n"
                f"4. Buffer time between meetings (at least 15 minutes)\n\n"
                f"Return exactly 3 suggestions in this format:\n"
                f"1. [DATE] [START_TIME] - [END_TIME]: [Brief reason]\n"
                f"2. [DATE] [START_TIME] - [END_TIME]: [Brief reason]\n"
                f"3. [DATE] [START_TIME] - [END_TIME]: [Brief reason]"
            )

            result = await ctx.session.create_message(
                CreateMessageRequestParams(
                    messages=[
                        SamplingMessage(
                            role="user",
                            content=SamplingTextContent(
                                type="text",
                                text=sampling_prompt
                            )
                        )
                    ],
                    maxTokens=500,
                    systemPrompt=(
                        "You are a scheduling assistant. Analyze the calendar and "
                        "suggest optimal time slots. Be specific with dates and times. "
                        "Consider work-life balance and productivity patterns."
                    )
                )
            )

            suggestion = result.content.text if hasattr(result.content, 'text') else str(result.content)

            return json.dumps({
                "success":      True,
                "activity":     activity,
                "duration":     duration,
                "date_range":   f"{date_from} to {date_to}",
                "suggestions":  suggestion,
                "events_checked": len(events)
            })

        except Exception as e:
            # fall back to basic slot finding if sampling fails
            pass

    # fallback — basic slot finding without sampling
    return json.dumps({
        "success":        True,
        "activity":       activity,
        "duration":       duration,
        "date_range":     f"{date_from} to {date_to}",
        "busy_slots":     [{"title": e["title"], "start": e["start"], "end": e["end"]} for e in events],
        "note":           "Sampling not available — showing busy slots so you can identify free time manually.",
        "events_checked": len(events)
    })


async def handle_create_recurring_event(args: dict, ctx=None) -> str:
    """
    Create a recurring event with complex recurrence rules.
    Uses sampling to parse natural language recurrence into RRULE.
    """
    import re
    from datetime import timedelta

    title           = args["title"]
    start           = args["start"]
    duration        = args.get("duration_minutes", 60)
    recurrence_desc = args["recurrence"]
    description     = args.get("description", "")
    location        = args.get("location", "")
    tz              = args.get("timezone", "Africa/Lagos")
    end_condition   = args.get("end_condition", "")

    # 1. parse start time
    try:
        start_dt = datetime.fromisoformat(start)
    except ValueError:
        return json.dumps({"error": f"Invalid start time: {start}. Use ISO 8601."})

    # 2. generate RRULE via sampling
    rrule = None

    if ctx:
        try:
            from mcp.types import (
                CreateMessageRequestParams,
                SamplingMessage,
                TextContent as SamplingTextContent
            )

            rrule_prompt = (
                f"Convert this recurrence description to a valid iCalendar RRULE string:\n"
                f"Recurrence: {recurrence_desc}\n"
                f"End condition: {end_condition if end_condition else 'none specified — recurring indefinitely'}\n"
                f"Event starts on: {start}\n\n"
                f"Rules:\n"
                f"- Return ONLY the RRULE string, nothing else\n"
                f"- Start with RRULE:\n"
                f"- Use standard RFC 5545 format\n"
                f"- Examples:\n"
                f"  'every Monday' → RRULE:FREQ=WEEKLY;BYDAY=MO\n"
                f"  'every weekday' → RRULE:FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR\n"
                f"  'every 2 weeks' → RRULE:FREQ=WEEKLY;INTERVAL=2\n"
                f"  'first Monday of month' → RRULE:FREQ=MONTHLY;BYDAY=MO;BYSETPOS=1\n"
                f"  'last Friday of month' → RRULE:FREQ=MONTHLY;BYDAY=FR;BYSETPOS=-1\n"
                f"  'every month on the 15th' → RRULE:FREQ=MONTHLY;BYMONTHDAY=15\n"
                f"  'every day for 10 times' → RRULE:FREQ=DAILY;COUNT=10\n"
                f"  'every week until Dec 31 2026' → RRULE:FREQ=WEEKLY;UNTIL=20261231T000000Z"
            )

            result = await ctx.session.create_message(
                CreateMessageRequestParams(
                    messages=[
                        SamplingMessage(
                            role="user",
                            content=SamplingTextContent(
                                type="text",
                                text=rrule_prompt
                            )
                        )
                    ],
                    maxTokens=100,
                    systemPrompt=(
                        "You are an iCalendar RRULE expert. "
                        "Return only the RRULE string, no explanation, no markdown, "
                        "no backticks. Just the raw RRULE string starting with RRULE:"
                    )
                )
            )

            rrule_raw = result.content.text if hasattr(result.content, "text") else str(result.content)
            rrule = rrule_raw.strip()

            if not rrule.startswith("RRULE:"):
                rrule = f"RRULE:{rrule}" if not rrule.startswith("FREQ=") else f"RRULE:{rrule}"

        except Exception as e:
            logger.error(f"Sampling failed for RRULE generation: {e}")

    # fallback if sampling unavailable
    if not rrule:
        freq     = args.get("frequency", "WEEKLY").upper()
        interval = args.get("interval", 1)
        byday    = args.get("byday", "")
        count    = args.get("count", "")
        until    = args.get("until", "")

        rrule = f"RRULE:FREQ={freq};INTERVAL={interval}"
        if byday:
            rrule += f";BYDAY={byday}"
        if count:
            rrule += f";COUNT={count}"
        elif until:
            rrule += f";UNTIL={until}"

    # 3. correct start date based on BYDAY in rrule
    if rrule and "BYDAY=" in rrule:
        day_map = {"MO": 0, "TU": 1, "WE": 2, "TH": 3, "FR": 4, "SA": 5, "SU": 6}
        byday_match = re.search(r"BYDAY=([A-Z,]+)", rrule)
        if byday_match:
            days = [d.strip() for d in byday_match.group(1).split(",")]
            target_weekdays = sorted([day_map[d] for d in days if d in day_map])
            if target_weekdays:
                current_weekday = start_dt.weekday()
                days_ahead = None
                for target in target_weekdays:
                    diff = (target - current_weekday) % 7
                    if days_ahead is None or diff < days_ahead:
                        days_ahead = diff
                if days_ahead and days_ahead > 0:
                    start_dt = start_dt + timedelta(days=days_ahead)
                    logger.info(f"Corrected start date to {start_dt.isoformat()} ({start_dt.strftime('%A')})")

    # 4. build event with corrected start_dt
    end_dt = start_dt + timedelta(minutes=duration)

    event_body = {
        "summary":     title,
        "description": description,
        "location":    location,
        "start": {
            "dateTime": start_dt.isoformat(),
            "timeZone": tz
        },
        "end": {
            "dateTime": end_dt.isoformat(),
            "timeZone": tz
        },
        "recurrence": [rrule],
        "reminders": {
            "useDefault": False,
            "overrides": [
                {"method": "popup", "minutes": args.get("reminder_minutes", 30)}
            ]
        }
    }

    # 5. insert to Google Calendar
    svc = get_calendar_service()
    try:
        created = svc.events().insert(
            calendarId=CALENDAR_ID,
            body=event_body
        ).execute()

        return json.dumps({
            "success":    True,
            "message":    f"Recurring event '{title}' created successfully.",
            "rrule_used": rrule,
            "event":      _format_event(created)
        }, default=str)

    except Exception as e:
        return json.dumps({
            "error":   "failed_to_create",
            "message": str(e),
            "rrule":   rrule
        })