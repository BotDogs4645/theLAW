"""
Function calling framework for AI to execute functions.
OpenAI-only implementation.
"""
import asyncio
import time
import json
import re
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Set
from utils import logger
from utils.db import (
    get_schedules_by_date_range, get_schedules_by_sub_team,
    get_all_schedules, search_schedules, get_schedule_by_id
)
import logging
from utils.enums import SubTeam
import discord
import aiohttp
import config

class FunctionCaller:
    """Handles function calling for AI responses"""
    
    def __init__(self, bot: discord.Client):
        self.bot = bot
        self.logger = logger.get_logger(__name__)
        self.functions = {}
        self._register_functions()
        try:
            root_level = logging.getLogger().getEffectiveLevel()
            if root_level > logging.INFO:
                names = {getattr(h, 'name', None) for h in self.logger.handlers}
                if 'fc_stream' not in names:
                    sh = logging.StreamHandler()
                    sh.setLevel(logging.INFO)
                    sh.set_name('fc_stream')
                    fmt = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
                    sh.setFormatter(fmt)
                    self.logger.addHandler(sh)
                if 'fc_file' not in names:
                    fh = logging.FileHandler('bot.log')
                    fh.setLevel(logging.INFO)
                    fh.set_name('fc_file')
                    fmt = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
                    fh.setFormatter(fmt)
                    self.logger.addHandler(fh)
                # prevent double logging if root later drops to INFO
                self.logger.propagate = False
        except Exception:
            # Fail open; logging should not break bot
            pass
    
    def _stringify_for_log(self, data: Any) -> str:
        """Best-effort stringify for logging without raising serialization errors."""
        try:
            return json.dumps(data, ensure_ascii=False, default=str)
        except Exception:
            return str(data)
    
    def _register_functions(self):
        """Register all available functions"""
        self.functions = {
            "fetch_more_messages": self._fetch_more_messages,
            "think_harder": self._think_harder,
            "upload_code_file": self._upload_code_file,
            "read_attachment_file": self._read_attachment_file,
            "get_schedule_today": self._get_schedule_today,
            "get_schedule_date": self._get_schedule_date,
            "get_next_meeting": self._get_next_meeting,
            "find_meeting": self._find_meeting,
            "get_meeting_notes": self._get_meeting_notes,
        }

    async def _http_get_json(self, url: str, params: Optional[Dict[str, Any]] = None, timeout_seconds: float = config.HTTP_TIMEOUT_SECONDS) -> Dict[str, Any]:
        """Perform an HTTP GET and parse JSON with error handling."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, timeout=timeout_seconds) as resp:
                    status = resp.status
                    text = await resp.text()
                    if status != 200:
                        return {"success": False, "error": f"HTTP {status}", "status": status, "body": text[:500]}
                    try:
                        data = json.loads(text)
                    except Exception:
                        data = await resp.json(content_type=None)
                    return {"success": True, "status": status, "data": data}
        except asyncio.TimeoutError:
            return {"success": False, "error": "Request timed out"}
        except Exception as e:
            self.logger.error(f"HTTP GET failed: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    async def _fetch_more_messages(self, channel_id: Optional[int] = None, limit: int = 10, before_message_id: int = None, _context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        try:
            # auto-detection of channel from execution context if not provided
            if channel_id is None and _context and isinstance(_context.get("channel_id"), int):
                channel_id = _context.get("channel_id")

            channel = self.bot.get_channel(channel_id) if channel_id is not None else None
            if not channel: return {"success": False, "error": f"Channel {channel_id} not found"}
            messages_data = []
            before_obj = discord.Object(id=before_message_id) if before_message_id else None
            async for message in channel.history(limit=limit, before=before_obj):
                messages_data.append({"id": message.id, "author": message.author.display_name, "content": message.content})
            return {"success": True, "messages": list(reversed(messages_data))}
        except Exception as e:
            self.logger.error(f"Error fetching messages: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    async def _think_harder(self, problem_description: str, context: str = None) -> Dict[str, Any]:
        return {"success": True, "message": "Switching to advanced reasoning mode.", "use_pro_model": True, "problem": problem_description, "context": context}
    
    async def _upload_code_file(self, filename: str, content: str, language: str = "java") -> Dict[str, Any]:
        try:
            return {
                "success": True, 
                "message": f"Code file '{filename}' ready for upload",
                "filename": filename,
                "content": content,
                "language": language,
                "upload_file": True
            }
        except Exception as e:
            self.logger.error(f"Error preparing file upload: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    async def _read_attachment_file(self, message_id: int, channel_id: int, attachment_index: int = 0) -> Dict[str, Any]:
        try:
            channel = self.bot.get_channel(channel_id)
            if not channel: return {"success": False, "error": f"Channel {channel_id} not found"}
            msg = await channel.fetch_message(message_id)
            if not msg.attachments or attachment_index >= len(msg.attachments):
                return {"success": False, "error": "Attachment not found"}
            att = msg.attachments[attachment_index]
            if att.size > config.ATTACHMENT_MAX_SIZE_BYTES: return {"success": False, "error": f"Attachment too large (must be <= {config.ATTACHMENT_MAX_SIZE_BYTES // 1000}KB)"}
            
            content = (await att.read()).decode('utf-8', errors='replace')
            return {"success": True, "filename": att.filename, "content": content}
        except Exception as e:
            self.logger.error(f"Error reading attachment: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    async def _get_schedule_today(self) -> Dict[str, Any]:
        """Get all schedule items for today"""
        try:
            today = datetime.now().date()
            start_of_day = datetime.combine(today, datetime.min.time()).isoformat()
            end_of_day = datetime.combine(today, datetime.max.time()).isoformat()
            
            schedules = get_schedules_by_date_range(start_of_day, end_of_day)
            
            return {
                "success": True,
                "date": today.isoformat(),
                "count": len(schedules),
                "schedules": schedules
            }
        except Exception as e:
            self.logger.error(f"Error getting today's schedule: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    async def _get_schedule_date(self, date: str) -> Dict[str, Any]:
        """Get all schedule items for a specific date (YYYY-MM-DD format)"""
        try:
            target_date = datetime.strptime(date, "%Y-%m-%d").date()
            start_of_day = datetime.combine(target_date, datetime.min.time()).isoformat()
            end_of_day = datetime.combine(target_date, datetime.max.time()).isoformat()
            
            schedules = get_schedules_by_date_range(start_of_day, end_of_day)
            
            return {
                "success": True,
                "date": target_date.isoformat(),
                "count": len(schedules),
                "schedules": schedules
            }
        except ValueError:
            return {"success": False, "error": "Invalid date format. Use YYYY-MM-DD"}
        except Exception as e:
            self.logger.error(f"Error getting schedule for date {date}: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    async def _get_next_meeting(self, sub_team: str = None) -> Dict[str, Any]:
        """Get the next upcoming meeting, optionally filtered by subteam"""
        try:
            now = datetime.now().isoformat()
            
            if sub_team:
                if not SubTeam.is_valid(sub_team):
                    return {
                        "success": False, 
                        "error": f"Invalid subteam: {sub_team}. Valid options: {SubTeam.get_all_values()}"
                    }
                schedules = get_schedules_by_sub_team(sub_team)
            else:
                schedules = get_all_schedules()
            
            # filter for future meetings and sort by start time
            upcoming = [s for s in schedules if s['starts_at'] > now]
            upcoming.sort(key=lambda x: x['starts_at'])
            
            if upcoming:
                return {
                    "success": True,
                    "next_meeting": upcoming[0],
                    "sub_team_filter": sub_team
                }
            else:
                return {
                    "success": True,
                    "next_meeting": None,
                    "message": f"No upcoming meetings found{' for ' + sub_team if sub_team else ''}"
                }
        except Exception as e:
            self.logger.error(f"Error getting next meeting: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    async def _find_meeting(self, search_term: str) -> Dict[str, Any]:
        """Find meetings by searching title, description, or subteam"""
        try:
            schedules = search_schedules(search_term)
            
            return {
                "success": True,
                "search_term": search_term,
                "count": len(schedules),
                "meetings": schedules
            }
        except Exception as e:
            self.logger.error(f"Error finding meeting: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    async def _get_meeting_notes(self, meeting_id: int) -> Dict[str, Any]:
        """Get notes for a specific meeting by ID (for 'what did I miss' questions)"""
        try:
            schedule = get_schedule_by_id(meeting_id, include_notes=True)
            
            if not schedule:
                return {
                    "success": False,
                    "error": f"Meeting with ID {meeting_id} not found"
                }
            

            return {
                "success": True,
                "meeting": {
                    "id": schedule['id'],
                    "title": schedule['title'],
                    "sub_team": schedule['sub_team'],
                    "room": schedule['room'],
                    "starts_at": schedule['starts_at'],
                    "ends_at": schedule['ends_at'],
                    "teachers": schedule['teachers'],
                    "notes": schedule['notes'],
                    "slides_url": schedule['slides_url']
                }
            }
        except Exception as e:
            self.logger.error(f"Error getting meeting notes: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    def get_openai_tools(self, include: Optional[Set[str]] = None, exclude: Optional[Set[str]] = None) -> List[Dict[str, Any]]:
        """Get OpenAI-formatted tool definitions. Optionally filter by include/exclude sets of function names."""
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "fetch_more_messages",
                    "description": (
                        "Fetch additional recent messages from this channel ONLY when the user explicitly asks to see more/earlier messages "
                        "(e.g., 'scroll up', 'show previous messages', 'what did I miss above'). "
                        "Do not call based on your own initiative. channel_id is inferred; no need to pass it."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "limit": {"type": "integer", "description": "How many messages to fetch (<= 25)"},
                            "before_message_id": {"type": "integer", "description": "Fetch messages before this ID"}
                        }
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "think_harder",
                    "description": (
                        "Escalate to advanced reasoning model for complex FRC engineering problems requiring implementation, "
                        "debugging, or detailed calculations. Only call this from the lite model. Do not call from pro model. "
                        "Call at most once per user interaction."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "problem_description": {"type": "string", "description": "Brief description of why escalation is needed"},
                            "context": {"type": "string", "description": "Optional minimal context to carry forward"}
                        },
                        "required": ["problem_description"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "upload_code_file",
                    "description": (
                        "Upload a single complete SOURCE CODE file only when the generated code exceeds chat limits "
                        "(~>100 lines or >2000 chars). Never upload markdown/prose, instructions, or checklists. "
                        "Limit one upload per interaction. Prefer inline answers when possible."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "filename": {"type": "string", "description": "Name of the file to upload"},
                            "content": {"type": "string", "description": "Full source code content"},
                            "language": {"type": "string", "description": "Programming language (e.g., 'java', 'python')"}
                        },
                        "required": ["filename", "content"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "read_attachment_file",
                    "description": "Read a text attachment from a message in this channel.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "message_id": {"type": "integer", "description": "Discord message ID"},
                            "channel_id": {"type": "integer", "description": "Discord channel ID"},
                            "attachment_index": {"type": "integer", "description": "Index of attachment (default 0)"}
                        },
                        "required": ["message_id", "channel_id"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_schedule_today",
                    "description": "Get all schedule items for today.",
                    "parameters": {"type": "object", "properties": {}}
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_schedule_date",
                    "description": "Get all schedule items for a specific date (YYYY-MM-DD format).",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "date": {"type": "string", "description": "Date in YYYY-MM-DD format"}
                        },
                        "required": ["date"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_next_meeting",
                    "description": (
                        "Get the next upcoming meeting. If 'sub_team' is provided, filter by that subteam. "
                        "Use this to answer questions like 'when is the next meeting' or 'what's the next Software & Electronics meeting'."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "sub_team": {"type": "string", "description": "Optional subteam filter"}
                        }
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "find_meeting",
                    "description": (
                        "Search meetings by title, description, or subteam. Use when the user references a meeting loosely."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "search_term": {"type": "string", "description": "Search query"}
                        },
                        "required": ["search_term"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_meeting_notes",
                    "description": "Get meeting notes by ID. Use when answering 'what did I miss' or specific follow-ups about content.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "meeting_id": {"type": "integer", "description": "Meeting ID"}
                        },
                        "required": ["meeting_id"]
                    }
                }
            }
        ]

        if include:
            tools = [t for t in tools if t["function"]["name"] in include]
        if exclude:
            tools = [t for t in tools if t["function"]["name"] not in exclude]

        return tools

    async def execute_function(self, function_name: str, parameters: Dict[str, Any], *, _context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Execute a function by name with given parameters"""
        if function_name not in self.functions:
            return {"success": False, "error": f"Function '{function_name}' not found"}
        
        try:
            self.logger.info(
                f"[FunctionCall] name={function_name} args={self._stringify_for_log(parameters)}"
            )

            fn = self.functions[function_name]
            if _context is not None:
                try:
                    result = await fn(**parameters, _context=_context)
                except TypeError:
                    result = await fn(**parameters)
            else:
                result = await fn(**parameters)

            self.logger.info(
                f"[FunctionResult] name={function_name} response={self._stringify_for_log(result)}"
            )
            return result
        except Exception as e:
            self.logger.error(f"Error executing function {function_name}: {e}", exc_info=True)
            error_result = {"success": False, "error": str(e)}
            # still emit a result log so every call has a response line
            self.logger.info(
                f"[FunctionResult] name={function_name} response={self._stringify_for_log(error_result)}"
            )
            return error_result
            