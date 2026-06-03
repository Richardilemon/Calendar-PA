import os
import json
import logging
import asyncio
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes
)
import anthropic

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ANTHROPIC_API_KEY  = os.getenv("ANTHROPIC_API_KEY")
MCP_SERVER_PATH    = os.getenv(
    "MCP_SERVER_PATH",
    "/Users/gg/projects/calendar-pa/src/server.py"
)
PYTHON_PATH        = os.getenv(
    "PYTHON_PATH",
    "/Users/gg/projects/calendar-pa/venv/bin/python"
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Anthropic client
anthropic_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# System prompt for the calendar PA
def get_system_prompt() -> str:
    from datetime import datetime, timezone
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return f"""You are Calendar PA, a smart personal calendar assistant. 
You have access to the user's Google Calendar through MCP tools.

TODAY'S DATE IS {today}. This is the REAL current date. ALWAYS use this date.

CRITICAL RULES:
- NEVER answer calendar questions from memory or assumptions
- ALWAYS call get_events tool to check the actual calendar
- When user asks "what's on today", call get_events with date="{today}"
- NEVER guess or assume what's on the calendar

You can:
- Check what's on the calendar (get_events)
- Create new events (create_event) — always check for conflicts first
- Update existing events (update_event)
- Delete events (delete_event) — always confirm before deleting
- Find free time slots (find_free_slot)
- Create recurring events (create_recurring_event)
- Set reminders (set_reminder)
- Remember context across sessions (get_session_context, update_session_context)

Always:
1. Call get_session_context at the start of each conversation
2. Call get_events BEFORE answering any calendar question
3. Be concise — this is a chat interface, not an email
4. Confirm before making any changes
5. Update session context after completing significant actions
6. Use Africa/Lagos timezone by default unless told otherwise

Be friendly, efficient, and proactive about spotting scheduling conflicts."""

# conversation history per user
user_conversations: dict[int, list] = {}


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    await update.message.reply_text(
        "👋 Hi! I'm Calendar PA — your AI-powered Google Calendar assistant.\n\n"
        "I can help you:\n"
        "• Check your schedule\n"
        "• Create and manage events\n"
        "• Find free time slots\n"
        "• Set up recurring events\n\n"
        "Just tell me what you need in plain English.\n\n"
        "Use /connect to link your Google Calendar."
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command"""
    await update.message.reply_text(
        "📅 *Calendar PA Commands*\n\n"
        "/start — Welcome message\n"
        "/today — What's on today\n"
        "/week — This week's schedule\n"
        "/clear — Clear conversation history\n"
        "/help — This message\n\n"
        "Or just type naturally:\n"
        "• _'Schedule a meeting tomorrow at 3pm'_\n"
        "• _'Find me a 2 hour deep work block this week'_\n"
        "• _'What do I have on Friday?'_",
        parse_mode="Markdown"
    )


async def today_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /today command"""
    await handle_message_with_text(update, context, "What's on my calendar today?")


async def week_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /week command"""
    await handle_message_with_text(update, context, "Show me my schedule for this week")


async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /clear command — reset conversation history"""
    user_id = update.effective_user.id
    user_conversations[user_id] = []
    await update.message.reply_text("✅ Conversation history cleared.")


async def handle_message_with_text(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str
):
    """Process a message with given text"""
    user_id = update.effective_user.id

    # init conversation history for new users
    if user_id not in user_conversations:
        user_conversations[user_id] = []

    # show typing indicator
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id,
        action="typing"
    )

    # add user message to history
    user_conversations[user_id].append({
        "role": "user",
        "content": text
    })

    try:
        response = await call_claude_with_mcp(
            user_id=user_id,
            messages=user_conversations[user_id]
        )

        # add assistant response to history
        user_conversations[user_id].append({
            "role": "assistant",
            "content": response
        })

        # send response
        await update.message.reply_text(response)

    except Exception as e:
        logger.error(f"Error handling message: {e}")
        await update.message.reply_text(
            "Sorry, something went wrong. Please try again."
        )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle regular text messages"""
    await handle_message_with_text(update, context, update.message.text)


async def call_claude_with_mcp(user_id: int, messages: list) -> str:
    """
    Call Claude API with MCP server tools.
    Claude will call tools on our MCP server as needed.
    """
    import subprocess
    import threading

    # run the MCP interaction in a thread pool to avoid blocking
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None,
        lambda: _sync_claude_call(messages)
    )
    return result


def _sync_claude_call(messages: list) -> str:
    """
    Synchronous Claude API call with MCP tool use.
    Handles the tool use loop until Claude gives a final response.
    """
    # get available tools from our MCP server
    tools = _get_mcp_tools()

    current_messages = messages.copy()
    max_iterations   = 10  # prevent infinite loops

    for _ in range(max_iterations):
        response = anthropic_client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1000,
            system=get_system_prompt(),
            tools=tools,
            messages=current_messages
        )

        # if Claude wants to use a tool
        if response.stop_reason == "tool_use":
            # extract tool calls
            tool_calls    = [b for b in response.content if b.type == "tool_use"]
            text_blocks   = [b for b in response.content if b.type == "text"]

            # add assistant message with tool calls
            current_messages.append({
                "role":    "assistant",
                "content": response.content
            })

            # execute each tool call against our MCP server
            tool_results = []
            for tool_call in tool_calls:
                result = _call_mcp_tool(tool_call.name, tool_call.input)
                tool_results.append({
                    "type":        "tool_result",
                    "tool_use_id": tool_call.id,
                    "content":     result
                })

            # add tool results to messages
            current_messages.append({
                "role":    "user",
                "content": tool_results
            })

        else:
            # Claude gave a final text response
            text_parts = [b.text for b in response.content if hasattr(b, "text")]
            return " ".join(text_parts) if text_parts else "Done."

    return "Sorry, I got stuck in a loop. Please try again."


def _get_mcp_tools() -> list:
    """
    Returns the tool definitions for our MCP server
    in Anthropic API format.
    """
    return [
        {
            "name": "get_events",
            "description": "Fetch events from Google Calendar. Supports single date, date range, or keyword search. Use this before scheduling anything.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "date":        {"type": "string", "description": "Single date YYYY-MM-DD"},
                    "date_from":   {"type": "string", "description": "Start of range YYYY-MM-DD"},
                    "date_to":     {"type": "string", "description": "End of range YYYY-MM-DD"},
                    "query":       {"type": "string", "description": "Keyword search"},
                    "max_results": {"type": "integer", "description": "Max results, default 20"}
                }
            }
        },
        {
            "name": "create_event",
            "description": "Create a new event. Automatically checks for conflicts.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "title":            {"type": "string"},
                    "start":            {"type": "string", "description": "ISO 8601 datetime"},
                    "duration_minutes": {"type": "integer"},
                    "description":      {"type": "string"},
                    "location":         {"type": "string"},
                    "timezone":         {"type": "string"},
                    "reminder_minutes": {"type": "integer"}
                },
                "required": ["title", "start"]
            }
        },
        {
            "name": "update_event",
            "description": "Update an existing event. Use get_events first to find event_id.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "event_id":         {"type": "string"},
                    "title":            {"type": "string"},
                    "start":            {"type": "string"},
                    "duration_minutes": {"type": "integer"},
                    "description":      {"type": "string"},
                    "location":         {"type": "string"},
                    "timezone":         {"type": "string"},
                    "reminder_minutes": {"type": "integer"}
                },
                "required": ["event_id"]
            }
        },
        {
            "name": "delete_event",
            "description": "Delete an event. Requires confirmation.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "event_id": {"type": "string"},
                    "confirm":  {"type": "boolean"}
                },
                "required": ["event_id"]
            }
        },
        {
            "name": "find_free_slot",
            "description": "Find available time slots using AI reasoning.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "duration_minutes": {"type": "integer"},
                    "date_from":        {"type": "string"},
                    "date_to":          {"type": "string"},
                    "activity":         {"type": "string"},
                    "preferences":      {"type": "string"}
                }
            }
        },
        {
            "name": "create_recurring_event",
            "description": "Create a recurring event. Understands natural language recurrence.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "title":            {"type": "string"},
                    "start":            {"type": "string"},
                    "recurrence":       {"type": "string"},
                    "duration_minutes": {"type": "integer"},
                    "end_condition":    {"type": "string"},
                    "description":      {"type": "string"},
                    "location":         {"type": "string"},
                    "timezone":         {"type": "string"},
                    "reminder_minutes": {"type": "integer"}
                },
                "required": ["title", "start", "recurrence"]
            }
        },
        {
            "name": "set_reminder",
            "description": "Add or update a reminder on an existing event.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "event_id":         {"type": "string"},
                    "reminder_minutes": {"type": "integer"},
                    "method":           {"type": "string"}
                },
                "required": ["event_id"]
            }
        },
        {
            "name": "get_session_context",
            "description": "Load session context. ALWAYS call this first.",
            "input_schema": {
                "type": "object",
                "properties": {}
            }
        },
        {
            "name": "update_session_context",
            "description": "Save session state after completing a task.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "last_action":        {"type": "string"},
                    "last_event_created": {"type": "string"},
                    "pending_tasks":      {"type": "array", "items": {"type": "string"}},
                    "notes":              {"type": "string"},
                    "preferences":        {"type": "object"}
                }
            }
        }
    ]


def _call_mcp_tool(tool_name: str, arguments: dict) -> str:
    """
    Call a tool on our MCP server by importing and running it directly.
    This avoids subprocess overhead and keeps everything in-process.
    """
    import asyncio
    import sys
    import os

    # ensure project root is in path
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

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

    handler = handlers.get(tool_name)
    if not handler:
        return json.dumps({"error": f"Unknown tool: {tool_name}"})

    try:
        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(handler(arguments))
        loop.close()
        return result if isinstance(result, str) else json.dumps(result)
    except Exception as e:
        return json.dumps({"error": str(e)})


def main():
    """Start the Telegram bot"""
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # register handlers
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help",  help_command))
    app.add_handler(CommandHandler("today", today_command))
    app.add_handler(CommandHandler("week",  week_command))
    app.add_handler(CommandHandler("clear", clear_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Calendar PA bot starting...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()