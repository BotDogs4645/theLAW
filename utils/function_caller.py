"""
Function calling framework for AI to execute functions
"""
import asyncio
import time
import json
import re
from typing import Dict, List, Any, Optional, Callable
from utils import database, logger
import discord

class FunctionCaller:
    """Handles function calling for AI responses"""
    
    def __init__(self, bot: discord.Client):
        self.bot = bot
        self.logger = logger.get_logger(__name__)
        self.functions = {}
        self._register_functions()
    
    def _register_functions(self):
        """Register all available functions"""
        self.functions = {
            "fetch_more_messages": self._fetch_more_messages,
            "add_memory": self._add_memory,
            "update_memory": self._update_memory,
            "remove_memory": self._remove_memory,
            "get_memory": self._get_memory,
            "search_memories": self._search_memories,
            "list_memories": self._list_memories,
            "think_harder": self._think_harder,
            "upload_code_file": self._upload_code_file,
            "read_attachment_file": self._read_attachment_file
        }
    
    async def _fetch_more_messages(self, channel_id: int, limit: int = 10, before_message_id: int = None) -> Dict[str, Any]:
        """Fetch more messages from a channel by scrolling up"""
        try:
            channel = self.bot.get_channel(channel_id)
            if not channel:
                return {"success": False, "error": f"Channel {channel_id} not found"}
            
            messages = []
            before_obj = discord.Object(id=before_message_id) if before_message_id else None
            
            async for message in channel.history(limit=limit, before=before_obj):
                messages.append({
                    "id": message.id,
                    "author": message.author.display_name,
                    "username": message.author.name,
                    "content": message.content,
                    "timestamp": message.created_at.isoformat(),
                    "is_bot": message.author.bot
                })
            
            return {
                "success": True,
                "messages": list(reversed(messages)),  # Return in chronological order
                "count": len(messages)
            }
        except Exception as e:
            self.logger.error(f"Error fetching messages: {e}")
            return {"success": False, "error": str(e)}
    
    async def _add_memory(self, memory_key: str, memory_content: str, memory_type: str = "general", created_by_discord_id: int = None) -> Dict[str, Any]:
        """Add a new memory"""
        try:
            success = database.add_ai_memory(memory_key, memory_content, memory_type, created_by_discord_id)
            if success:
                return {"success": True, "message": f"Memory '{memory_key}' added successfully"}
            else:
                return {"success": False, "error": "Failed to add memory (key may already exist)"}
        except Exception as e:
            self.logger.error(f"Error adding memory: {e}")
            return {"success": False, "error": str(e)}
    
    async def _update_memory(self, memory_key: str, memory_content: str, memory_type: str = None) -> Dict[str, Any]:
        """Update an existing memory"""
        try:
            success = database.update_ai_memory(memory_key, memory_content, memory_type)
            if success:
                return {"success": True, "message": f"Memory '{memory_key}' updated successfully"}
            else:
                return {"success": False, "error": "Memory not found or update failed"}
        except Exception as e:
            self.logger.error(f"Error updating memory: {e}")
            return {"success": False, "error": str(e)}
    
    async def _remove_memory(self, memory_key: str) -> Dict[str, Any]:
        """Remove a memory"""
        try:
            success = database.delete_ai_memory(memory_key)
            if success:
                return {"success": True, "message": f"Memory '{memory_key}' removed successfully"}
            else:
                return {"success": False, "error": "Memory not found"}
        except Exception as e:
            self.logger.error(f"Error removing memory: {e}")
            return {"success": False, "error": str(e)}
    
    async def _get_memory(self, memory_key: str) -> Dict[str, Any]:
        """Get a specific memory"""
        try:
            memory = database.get_ai_memory(memory_key)
            if memory:
                return {"success": True, "memory": memory}
            else:
                return {"success": False, "error": "Memory not found"}
        except Exception as e:
            self.logger.error(f"Error getting memory: {e}")
            return {"success": False, "error": str(e)}
    
    async def _search_memories(self, search_term: str) -> Dict[str, Any]:
        """Search memories by content"""
        try:
            memories = database.search_ai_memories(search_term)
            return {"success": True, "memories": memories, "count": len(memories)}
        except Exception as e:
            self.logger.error(f"Error searching memories: {e}")
            return {"success": False, "error": str(e)}
    
    async def _list_memories(self, memory_type: str = None) -> Dict[str, Any]:
        """List all memories, optionally filtered by type"""
        try:
            memories = database.get_all_ai_memories(memory_type)
            return {"success": True, "memories": memories, "count": len(memories)}
        except Exception as e:
            self.logger.error(f"Error listing memories: {e}")
            return {"success": False, "error": str(e)}
    
    async def _think_harder(self, problem_description: str, context: str = None) -> Dict[str, Any]:
        """Use the more powerful Gemini 2.5 Pro model for complex coding problems"""
        try:
            # This function will be handled specially in the AI mention cog
            # It returns a signal that the AI should use the 2.5 Pro model
            return {
                "success": True, 
                "message": "Switching to advanced reasoning mode",
                "use_pro_model": True,
                "problem": problem_description,
                "context": context
            }
        except Exception as e:
            self.logger.error(f"Error in think_harder: {e}")
            return {"success": False, "error": str(e)}
    
    async def _upload_code_file(self, filename: str, content: str, language: str = "java") -> Dict[str, Any]:
        """Upload a code file to Discord"""
        try:
            # This function will be handled specially in the AI mention cog
            # It returns a signal that the AI wants to upload a file
            return {
                "success": True,
                "message": "File upload requested",
                "upload_file": True,
                "filename": filename,
                "content": content,
                "language": language
            }
        except Exception as e:
            self.logger.error(f"Error in upload_code_file: {e}")
            return {"success": False, "error": str(e)}

    async def _read_attachment_file(self, message_id: int, channel_id: int, attachment_index: int = 0) -> Dict[str, Any]:
        """Read a small text attachment (<=3KB) from a message and return its content."""
        try:
            channel = self.bot.get_channel(channel_id)
            if not channel:
                return {"success": False, "error": f"Channel {channel_id} not found"}
            try:
                msg = await channel.fetch_message(message_id)
            except discord.NotFound:
                return {"success": False, "error": f"Message {message_id} not found"}
            except Exception as e:
                return {"success": False, "error": f"Failed to fetch message: {e}"}

            if not msg.attachments:
                return {"success": False, "error": "No attachments on the referenced message"}
            if attachment_index < 0 or attachment_index >= len(msg.attachments):
                return {"success": False, "error": f"attachment_index {attachment_index} out of range"}
            att = msg.attachments[attachment_index]

            # Validate size and type
            if att.size is None or att.size > 3 * 1024:
                return {"success": False, "error": "Attachment too large (must be <= 3KB)"}
            content_type = getattr(att, 'content_type', None) or ''
            filename = att.filename or "file.txt"
            is_text = content_type.startswith('text/') or any(filename.endswith(ext) for ext in [
                '.txt', '.md', '.csv', '.json', '.yaml', '.yml', '.py', '.java', '.cpp', '.h', '.hpp', '.js', '.ts', '.html', '.css'
            ])
            if not is_text:
                return {"success": False, "error": f"Unsupported attachment type for inline read: {content_type or 'unknown'}"}

            data = await att.read()
            try:
                text = data.decode('utf-8', errors='replace')
            except Exception:
                text = data.decode('latin-1', errors='replace')
            return {
                "success": True,
                "message": "Attachment read successfully",
                "filename": filename,
                "content_type": content_type,
                "size": att.size,
                "content": text
            }
        except Exception as e:
            self.logger.error(f"Error in read_attachment_file: {e}")
            return {"success": False, "error": str(e)}
    
    def get_function_schema(self) -> List[Dict[str, Any]]:
        """Get the schema for all available functions"""
        return [
            {
                "name": "fetch_more_messages",
                "description": "Fetch more messages from a channel by scrolling up in the chat history",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "channel_id": {"type": "integer", "description": "The Discord channel ID to fetch messages from"},
                        "limit": {"type": "integer", "description": "Number of messages to fetch (default: 10)", "default": 10},
                        "before_message_id": {"type": "integer", "description": "Message ID to fetch messages before (optional)"}
                    },
                    "required": ["channel_id"]
                }
            },
            {
                "name": "add_memory",
                "description": "Add a new memory to the AI's knowledge base",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "memory_key": {"type": "string", "description": "Unique key for the memory"},
                        "memory_content": {"type": "string", "description": "The content to store in the memory"},
                        "memory_type": {"type": "string", "description": "Type/category of the memory (default: general)", "default": "general"},
                        "created_by_discord_id": {"type": "integer", "description": "Discord ID of the user who created this memory (optional)"}
                    },
                    "required": ["memory_key", "memory_content"]
                }
            },
            {
                "name": "update_memory",
                "description": "Update an existing memory in the AI's knowledge base",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "memory_key": {"type": "string", "description": "Key of the memory to update"},
                        "memory_content": {"type": "string", "description": "New content for the memory"},
                        "memory_type": {"type": "string", "description": "New type/category for the memory (optional)"}
                    },
                    "required": ["memory_key", "memory_content"]
                }
            },
            {
                "name": "remove_memory",
                "description": "Remove a memory from the AI's knowledge base",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "memory_key": {"type": "string", "description": "Key of the memory to remove"}
                    },
                    "required": ["memory_key"]
                }
            },
            {
                "name": "get_memory",
                "description": "Get a specific memory by its key",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "memory_key": {"type": "string", "description": "Key of the memory to retrieve"}
                    },
                    "required": ["memory_key"]
                }
            },
            {
                "name": "search_memories",
                "description": "Search memories by content or key",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "search_term": {"type": "string", "description": "Term to search for in memory content or keys"}
                    },
                    "required": ["search_term"]
                }
            },
            {
                "name": "list_memories",
                "description": "List all memories, optionally filtered by type",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "memory_type": {"type": "string", "description": "Type of memories to list (optional)"}
                    },
                    "required": []
                }
            },
            {
                "name": "think_harder",
                "description": "Use advanced reasoning mode with Gemini 2.5 Pro for complex coding problems, APIs, or difficult technical questions",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "problem_description": {"type": "string", "description": "Description of the complex problem or coding challenge"},
                        "context": {"type": "string", "description": "Additional context about the problem (optional)"}
                    },
                    "required": ["problem_description"]
                }
            },
            {
                "name": "upload_code_file",
                "description": "Upload a code file to Discord when the code is too long for a message (over 5 lines)",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "filename": {"type": "string", "description": "Name of the file with proper extension (e.g., 'KrakenSubsystem.java', 'Robot.java')"},
                        "content": {"type": "string", "description": "The code content to upload"},
                        "language": {"type": "string", "description": "Programming language for syntax highlighting (e.g., 'java', 'cpp', 'python')", "default": "java"}
                    },
                    "required": ["filename", "content"]
                }
            },
            {
                "name": "read_attachment_file",
                "description": "Read a small text attachment (<=3KB) from a specific message",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "message_id": {"type": "integer", "description": "The Discord message ID that has the attachment"},
                        "channel_id": {"type": "integer", "description": "The Discord channel ID of the message"},
                        "attachment_index": {"type": "integer", "description": "Index of the attachment on that message (default 0)", "default": 0}
                    },
                    "required": ["message_id", "channel_id"]
                }
            }
        ]
    
    async def execute_function(self, function_name: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a function by name with given parameters"""
        if function_name not in self.functions:
            return {"success": False, "error": f"Function '{function_name}' not found"}
        
        try:
            param_keys = list(parameters.keys())
            # Avoid logging huge payloads; just log keys and a short preview
            preview = repr(parameters)
            if len(preview) > 300:
                preview = preview[:300] + '...'
            self.logger.debug(f"Executing function '{function_name}' with params keys: {param_keys} preview: {preview}")
            start_time = time.time()
            result = await self.functions[function_name](**parameters)
            elapsed_ms = (time.time() - start_time) * 1000.0
            # Summarize result for logs
            result_keys = list(result.keys()) if isinstance(result, dict) else []
            result_preview = repr(result)
            if len(result_preview) > 300:
                result_preview = result_preview[:300] + '...'
            self.logger.debug(
                f"Function '{function_name}' completed in {elapsed_ms:.1f}ms; result keys: {result_keys}; preview: {result_preview}"
            )
            return result
        except Exception as e:
            self.logger.error(f"Error executing function {function_name}: {e}")
            return {"success": False, "error": str(e)}
    
    def _extract_balanced_json(self, text: str, start_index: int) -> Optional[Dict[str, Any]]:
        """Extract a balanced JSON object starting at start_index (which should point to '{').

        Returns a dict with keys: json_str (the substring), end_index (index after the JSON), or None if failed.
        """
        if start_index >= len(text) or text[start_index] != '{':
            return None
        i = start_index
        brace_depth = 0
        in_string = False
        escape_next = False
        while i < len(text):
            ch = text[i]
            if in_string:
                if escape_next:
                    escape_next = False
                elif ch == '\\':
                    escape_next = True
                elif ch == '"':
                    in_string = False
            else:
                if ch == '"':
                    in_string = True
                elif ch == '{':
                    brace_depth += 1
                elif ch == '}':
                    brace_depth -= 1
                    if brace_depth == 0:
                        # include this closing brace
                        json_str = text[start_index:i+1]
                        return {"json_str": json_str, "end_index": i + 1}
            i += 1
        return None

    def parse_function_calls(self, text: str) -> List[Dict[str, Any]]:
        """Parse function calls from AI response text using balanced-brace JSON extraction."""
        function_calls: List[Dict[str, Any]] = []
        # Debug logging (truncate to reduce noise)
        self.logger.debug("Function call parsing - Text (truncated): %s", repr(text)[:600])

        idx = 0
        while idx < len(text):
            # Find the next tag like <functionName> or </functionName>
            tag_match = re.search(r'<\/?(\w+)\s*>', text[idx:])
            if not tag_match:
                break
            fn_name = tag_match.group(1)
            tag_start = idx + tag_match.start()
            tag_end = idx + tag_match.end()
            # After the tag, skip whitespace to the JSON object
            j = tag_end
            while j < len(text) and text[j].isspace():
                j += 1
            if j >= len(text) or text[j] != '{':
                idx = tag_end
                continue
            extracted = self._extract_balanced_json(text, j)
            if not extracted:
                idx = tag_end
                continue
            params_json = extracted["json_str"]
            idx = extracted["end_index"]
            # Optionally skip a closing tag like </functionName>
            closing_match = re.match(r'\s*</%s\s*>' % re.escape(fn_name), text[idx:])
            if closing_match:
                idx += closing_match.end()
            # Try strict parse first
            try:
                parameters = json.loads(params_json)
            except json.JSONDecodeError as e:
                # Attempt to sanitize: escape literal newlines/tabs/returns inside string literals
                self.logger.warning(f"Strict JSON parse failed for {fn_name}: {e}. Attempting sanitization.")
                sanitized = self._escape_control_chars_inside_strings(params_json)
                try:
                    parameters = json.loads(sanitized)
                except json.JSONDecodeError as e2:
                    self.logger.warning(f"Sanitized JSON parse failed for {fn_name}: {e2}")
                    self.logger.warning(f"Raw params string (truncated): {repr(params_json[:200])}...")
                    continue
            function_calls.append({"name": fn_name, "parameters": parameters})
            params_preview = params_json if len(params_json) <= 400 else params_json[:400] + '...'
            self.logger.debug(f"Successfully parsed function call: {fn_name}; params length: {len(params_json)}; preview: {params_preview}")
        self.logger.debug(f"Function call parsing - Matches found: {[c['name'] for c in function_calls]}")
        return function_calls
    
    def remove_function_calls_from_text(self, text: str) -> str:
        """Remove function call segments like <fn>{...} from text using balanced JSON parsing."""
        result_parts: List[str] = []
        idx = 0
        while idx < len(text):
            tag_match = re.search(r'<\/?(\w+)\s*>', text[idx:])
            if not tag_match:
                result_parts.append(text[idx:])
                break
            tag_start = idx + tag_match.start()
            tag_end = idx + tag_match.end()
            # append text before the tag
            result_parts.append(text[idx:tag_start])
            # move to after tag
            j = tag_end
            while j < len(text) and text[j].isspace():
                j += 1
            if j < len(text) and text[j] == '{':
                extracted = self._extract_balanced_json(text, j)
                if extracted:
                    # skip over the JSON object
                    idx = extracted["end_index"]
                    # Optionally skip a closing tag if present
                    closing_name = tag_match.group(1)
                    closing_match = re.match(r'\s*</%s\s*>' % re.escape(closing_name), text[idx:])
                    if closing_match:
                        idx += closing_match.end()
                    continue
            # if no JSON after tag, just skip the tag and continue
            idx = tag_end
        cleaned_text = ''.join(result_parts)
        # Normalize whitespace a bit
        cleaned_text = re.sub(r'\n\s*\n', '\n\n', cleaned_text)
        cleaned_text = cleaned_text.strip()
        return cleaned_text

    def _escape_control_chars_inside_strings(self, json_text: str) -> str:
        """Escape literal control characters (\n, \r, \t) that appear inside JSON string literals.

        This keeps content identical while producing JSON that json.loads can parse.
        """
        result_chars: List[str] = []
        in_string = False
        escape_next = False
        for ch in json_text:
            if in_string:
                if escape_next:
                    result_chars.append(ch)
                    escape_next = False
                    continue
                if ch == '\\':
                    result_chars.append(ch)
                    escape_next = True
                    continue
                if ch == '"':
                    result_chars.append(ch)
                    in_string = False
                    continue
                if ch == '\n':
                    result_chars.append('\\n')
                    continue
                if ch == '\r':
                    result_chars.append('\\r')
                    continue
                if ch == '\t':
                    result_chars.append('\\t')
                    continue
                # default inside string
                result_chars.append(ch)
            else:
                if ch == '"':
                    result_chars.append(ch)
                    in_string = True
                else:
                    result_chars.append(ch)
        return ''.join(result_chars)
