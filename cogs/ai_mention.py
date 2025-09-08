"""
AI mention response cog for handling bot mentions with Google Gemini API
"""
import discord
from discord.ext import commands
from utils.cog_base import BaseCog
from utils import logger, function_caller, prompt_loader
import asyncio
import re
import json
from typing import List, Dict, Optional
from google import genai
from google.genai import types
import config
from datetime import datetime, timezone
import math

class AIMentionCog(BaseCog):
    """Cog for handling bot mentions with AI responses using Google Gemini API"""
    
    def __init__(self, bot: commands.Bot):
        super().__init__(bot)
        self.client = None
        self.model_loaded = False
        self.model_loading = False
        self.function_caller = function_caller.FunctionCaller(bot)
        self.system_prompt = config.AI_SYSTEM_PROMPT
        self.advanced_system_prompt = config.AI_ADVANCED_SYSTEM_PROMPT
        
    async def cog_load(self):
        """Load the cog and initialize Gemini API"""
        super().cog_load()
        await self._initialize_gemini()
    
    async def _initialize_gemini(self):
        """Initialize Gemini API"""
        if self.model_loading or self.model_loaded:
            return
            
        self.model_loading = True
        try:
            # Initialize the new Gemini client
            self.client = genai.Client(api_key=config.AI_GEMINI_API_KEY)
            
            self.model_loaded = True
            self.logger.info(f"Gemini API initialized with models: {config.AI_GEMINI_MODEL} and {config.AI_GEMINI_PRO_MODEL}")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize Gemini API: {e}")
        finally:
            self.model_loading = False
    
    def _clean_message_content(self, content: str) -> str:
        """Clean message content by removing mentions and timing info"""
        # Remove Discord mentions
        content = re.sub(r'<@!?\d+>', '', content).strip()
        
        # Remove timing information that the bot might have added
        content = re.sub(r'\n\n-# Took \d+ms.*?$', '', content)
        content = re.sub(r'-# Took \d+ms.*?$', '', content)
        content = re.sub(r'\(called:.*?\)', '', content)  # Remove fake function call info
        
        return ' '.join(content.split())
    
    
    async def _get_recent_messages(self, channel: discord.TextChannel, limit: int = 20, before_message: discord.Message = None) -> List[discord.Message]:
        """Get recent messages from a channel"""
        messages = []
        async for message in channel.history(limit=limit, before=before_message):
            messages.append(message)
        return list(reversed(messages))
    
    async def _get_replied_message(self, message: discord.Message) -> discord.Message:
        """Get the message that this message is replying to"""
        if message.reference and message.reference.message_id:
            try:
                replied_message = await message.channel.fetch_message(message.reference.message_id)
                return replied_message
            except discord.NotFound:
                self.logger.warning(f"Could not find replied message {message.reference.message_id}")
                return None
            except Exception as e:
                self.logger.error(f"Error fetching replied message: {e}")
                return None
        return None
    
    def _format_context_for_gemini(self, history: List[discord.Message], user_question: str, current_user: discord.Member, replied_message: discord.Message = None, system_hint: Optional[str] = None) -> str:
        """formats the conversation for AI with display names and usernames"""
        
        # build the conversation context
        context_parts = [self._decorate_system_prompt_with_time(self.system_prompt)]
        if system_hint:
            context_parts.append(f"\n\nSYSTEM: Suggested auto-reply hint for this message: {system_hint}")
        context_parts.append("\n\n### Recent Chat Context:")

        # Add historical messages with display names and usernames for context
        for msg in history:
            content = self._clean_message_content(msg.content)
            if not content:
                continue
            
            # Get display name and username for better context
            display_name = msg.author.display_name
            username = msg.author.name
            
            # Create speaker info with both display name and username
            if display_name != username:
                speaker_info = f"{display_name} ({username})"
            else:
                speaker_info = display_name
            
            # Add speaker context to the message content
            if msg.author.id == self.bot.user.id:
                # Bot messages
                context_parts.append(f"the LAW: {content}")
            else:
                # User messages - add speaker info for context
                context_parts.append(f"{speaker_info}: {content}")

            # List attachments on this message, if any
            if getattr(msg, 'attachments', None):
                for i, att in enumerate(msg.attachments):
                    size = getattr(att, 'size', 0) or 0
                    ctype = getattr(att, 'content_type', '') or ''
                    context_parts.append(f"  - Attachment[{i}]: {att.filename} ({size} bytes, {ctype})")

        # Add the current user's message with proper identification
        current_display_name = current_user.display_name
        current_username = current_user.name
        
        if current_display_name != current_username:
            current_speaker_info = f"{current_display_name} ({current_username})"
        else:
            current_speaker_info = current_display_name
        
        # Check if this is a reply and add context
        if replied_message:
            replied_content = self._clean_message_content(replied_message.content)
            if replied_content:
                # Get the author info for the replied message
                replied_display_name = replied_message.author.display_name
                replied_username = replied_message.author.name
                
                if replied_display_name != replied_username:
                    replied_speaker_info = f"{replied_display_name} ({replied_username})"
                else:
                    replied_speaker_info = replied_display_name
                
                # Add reply context
                context_parts.append(f"\n### Replying to:")
                if replied_message.author.id == self.bot.user.id:
                    context_parts.append(f"the LAW: {replied_content}")
                else:
                    context_parts.append(f"{replied_speaker_info}: {replied_content}")
                # List attachments on replied message
                if getattr(replied_message, 'attachments', None):
                    for i, att in enumerate(replied_message.attachments):
                        size = getattr(att, 'size', 0) or 0
                        ctype = getattr(att, 'content_type', '') or ''
                        context_parts.append(f"  - Attachment[{i}]: {att.filename} ({size} bytes, {ctype})")
                context_parts.append(f"\n{current_speaker_info} (replying): {user_question}")
            else:
                context_parts.append(f"{current_speaker_info}: {user_question}")
        else:
            context_parts.append(f"{current_speaker_info}: {user_question}")

        # Join all parts
        return "\n".join(context_parts)

    def _decorate_system_prompt_with_time(self, base_prompt: str) -> str:
        """Append current local time (with timezone) and UTC time to the system prompt.

        The time block is appended at the bottom of the system prompt so the model
        has accurate temporal context. Uses ISO-like formats and explicit TZ.
        """
        try:
            local_now = datetime.now().astimezone()
            utc_now = datetime.now(timezone.utc)

            # Format offset as ±HH:MM from %z (±HHMM)
            offset_raw = local_now.strftime('%z')
            offset_fmt = f"{offset_raw[:3]}:{offset_raw[3:]}" if offset_raw and len(offset_raw) == 5 else offset_raw
            tz_name = local_now.tzname() or "Local"

            local_str = local_now.strftime('%Y-%m-%d %H:%M:%S')
            utc_str = utc_now.strftime('%Y-%m-%d %H:%M:%S')

            time_block = (
                "\n\n### Time Context\n"
                f"Local time: {local_str} {tz_name} (UTC{offset_fmt})\n"
                f"UTC time:   {utc_str} UTC"
            )
            return f"{base_prompt}{time_block}"
        except Exception:
            # If anything goes wrong, fall back to base prompt
            return base_prompt

    def _extract_relevant_handbook(self, user_question: str, max_chars: int = 1200) -> str:
        """Extract a relevant excerpt from the experience handbook for grounding.

        Simple keyword windowing around lines that match terms in the user question.
        Keeps the excerpt short to avoid blowing context.
        """
        try:
            text = prompt_loader.load_experience_prompt()
        except Exception:
            return ""
        if not text:
            return ""

        try:
            lines = text.splitlines()
            lower_lines = [ln.lower() for ln in lines]
            q = (user_question or "").lower()

            domain_terms = [
                "intake", "intakes", "elevator", "elevators", "climber", "climbers",
                "arm", "arms", "swerve", "drivetrain", "shooter", "indexer",
                "compression", "roller", "rollers", "belt", "chain",
            ]
            q_tokens = [t.strip(".,!?()[]{}:\"'") for t in q.split()]
            q_keywords = set([t for t in q_tokens if len(t) >= 5])
            q_keywords.update([t for t in domain_terms if t in q])
            if not q_keywords:
                q_keywords = {"intake", "elevator"}

            matches = []
            for idx, ln in enumerate(lower_lines):
                score = sum(1 for kw in q_keywords if kw in ln)
                if score > 0:
                    matches.append((idx, score))

            if not matches:
                return ""

            matches.sort(key=lambda x: (-x[1], x[0]))
            selected = [i for i, _ in matches[:3]]
            window = 8
            gathered = []
            seen = set()
            for i in selected:
                start = max(0, i - window)
                end = min(len(lines), i + window + 1)
                for j in range(start, end):
                    if j not in seen:
                        seen.add(j)
                        gathered.append(lines[j])

            excerpt = "\n".join(gathered).strip()
            if len(excerpt) > max_chars:
                cut = excerpt[:max_chars]
                # Try to end on a line boundary
                if "\n" in cut:
                    cut = cut.rsplit("\n", 1)[0]
                excerpt = cut.rstrip() + "\n..."
            return excerpt
        except Exception:
            return ""

    def _estimate_token_count_from_text(self, text: str) -> int:
        """Rough token estimate. Falls back when API token counting isn't available.

        Uses an approximate heuristic of ~4 characters per token, which is
        sufficient for debug display purposes.
        """
        try:
            if not text:
                return 0
            # Approximate tokens as characters/4, rounded up
            return int(math.ceil(len(text) / 4.0))
        except Exception:
            return 0

    def _count_tokens_for_model(self, model: str, text: str) -> int:
        """Try to count tokens using the Gemini SDK; fallback to estimate on failure."""
        try:
            if not text:
                return 0
            contents = [
                types.Content(
                    role="user",
                    parts=[types.Part.from_text(text=text)],
                ),
            ]
            try:
                result = self.client.models.count_tokens(
                    model=model,
                    contents=contents,
                )
                if isinstance(result, dict):
                    return int(result.get("total_tokens") or result.get("total_token_count") or 0) or self._estimate_token_count_from_text(text)
                for attr in ("total_tokens", "total_token_count", "input_tokens"):
                    if hasattr(result, attr):
                        value = getattr(result, attr)
                        if isinstance(value, (int, float)):
                            return int(value)
                return self._estimate_token_count_from_text(text)
            except Exception:
                return self._estimate_token_count_from_text(text)
        except Exception:
            return 0

    def _count_tokens_for_model_with_method(self, model: str, text: str) -> tuple[int, str]:
        """Return (token_count, method) where method is 'sdk' or 'est'."""
        try:
            if not text:
                return 0, 'sdk'
            contents = [
                types.Content(
                    role="user",
                    parts=[types.Part.from_text(text=text)],
                ),
            ]
            try:
                result = self.client.models.count_tokens(
                    model=model,
                    contents=contents,
                )
                if isinstance(result, dict):
                    value = int(result.get("total_tokens") or result.get("total_token_count") or 0)
                else:
                    value = 0
                    for attr in ("total_tokens", "total_token_count", "input_tokens"):
                        if hasattr(result, attr):
                            v = getattr(result, attr)
                            if isinstance(v, (int, float)):
                                value = int(v)
                                break
                if value > 0:
                    return value, 'sdk'
                return self._estimate_token_count_from_text(text), 'est'
            except Exception:
                return self._estimate_token_count_from_text(text), 'est'
        except Exception:
            return 0, 'est'

    def _get_model_context_window(self, model: str) -> Optional[int]:
        """Try to retrieve the model's max context window from the SDK; None if unavailable."""
        try:
            try:
                model_info = self.client.models.get(name=model)
                for attr in (
                    "input_token_limit",
                    "context_window",
                    "max_input_tokens",
                    "max_context_length",
                ):
                    if hasattr(model_info, attr):
                        value = getattr(model_info, attr)
                        if isinstance(value, (int, float)):
                            return int(value)
                if isinstance(model_info, dict):
                    for key in ("input_token_limit", "context_window", "max_input_tokens", "max_context_length"):
                        if key in model_info and isinstance(model_info[key], (int, float)):
                            return int(model_info[key])
            except Exception:
                try:
                    for m in self.client.models.list():
                        name = getattr(m, "name", None) or (m.get("name") if isinstance(m, dict) else None)
                        if name and model in name:
                            for attr in (
                                "input_token_limit",
                                "context_window",
                                "max_input_tokens",
                                "max_context_length",
                            ):
                                if hasattr(m, attr):
                                    value = getattr(m, attr)
                                    if isinstance(value, (int, float)):
                                        return int(value)
                                elif isinstance(m, dict) and attr in m and isinstance(m[attr], (int, float)):
                                    return int(m[attr])
                except Exception:
                    pass
            return None
        except Exception:
            return None

    async def _generate_response(self, prompt: str, channel_id: int = None, user_id: int = None) -> tuple[str, float, list[str], list[dict]]:
        """Generate AI response using Gemini API with function calling support.

        Returns a tuple of (response_text, response_time_ms, executed_functions, function_results).
        """
        if not self.model_loaded:
            return "im still loading my brain hold on", 0.0, [], []

        try:
            import time
            start_time = time.time()
            
            raw_response = await asyncio.get_event_loop().run_in_executor(
                None, 
                self._generate_response_sync, 
                prompt
            )
            
            # check for function calls in the RAW response BEFORE any cleaning
            self.logger.debug("Parsing function calls from raw response (len=%d)...", len(raw_response) if raw_response else 0)
            function_calls = self.function_caller.parse_function_calls(raw_response)
            executed_functions = []
            function_results = []
            
            if function_calls:
                self.logger.debug("Found %d function calls in response: %s", len(function_calls), [call['name'] for call in function_calls])
            else:
                self.logger.debug("No function calls found in AI response")
            
            if function_calls:
                think_harder_called = any(call["name"] == "think_harder" for call in function_calls)
                upload_file_called = any(call["name"] == "upload_code_file" for call in function_calls)
                
                # execute function calls
                function_results = []
                for call in function_calls:
                    self.logger.debug("Preparing to execute function '%s' with params keys: %s", call["name"], list(call.get("parameters", {}).keys()))
                    # add channel_id and user_id to parameters if available
                    if call["name"] == "fetch_more_messages" and channel_id and "channel_id" not in call["parameters"]:
                        call["parameters"]["channel_id"] = channel_id
                    if call["name"] == "read_attachment_file" and channel_id and "channel_id" not in call["parameters"]:
                        call["parameters"]["channel_id"] = channel_id
                    if call["name"] == "read_attachment_file" and "message_id" not in call["parameters"] and replied_message:
                        # if replying to a message with attachment, default to that message
                        call["parameters"]["message_id"] = replied_message.id
                    if call["name"] in ["add_memory", "update_memory"] and user_id and "created_by_discord_id" not in call["parameters"]:
                        call["parameters"]["created_by_discord_id"] = user_id
                    
                    result = await self.function_caller.execute_function(call["name"], call["parameters"])
                    self.logger.debug("Function '%s' returned keys: %s", call["name"], list(result.keys()) if isinstance(result, dict) else [])
                    function_results.append({
                        "function": call["name"],
                        "result": result
                    })
                    executed_functions.append(call["name"])
                
                # log function execution
                self.logger.debug("Executed %d function calls: %s", len(function_calls), executed_functions)
                
                # if we executed functions, generate a new response with the function results
                if function_results:
                    # build context from function results
                    function_context = "\n\n### Additional Context from Recent Messages:\n"
                    for func_result in function_results:
                        if func_result['function'] == 'fetch_more_messages':
                            if func_result['result'].get('success'):
                                messages = func_result['result'].get('messages', [])
                                function_context += f"Here are the recent messages from the channel:\n\n"
                                for msg in messages:
                                    author = msg.get('author', 'Unknown')
                                    content = msg.get('content', '')
                                    if content:
                                        function_context += f"{author}: {content}\n"
                                function_context += "\n"
                            else:
                                function_context += f"Failed to fetch messages: {func_result['result'].get('error', 'Unknown error')}\n"
                        elif func_result['function'] == 'think_harder':
                            # extract problem description and context for pro model
                            problem_desc = func_result['result'].get('problem', '')
                            context_info = func_result['result'].get('context', '')
                            function_context += f"\n### Complex Problem Analysis Mode:\n"
                            function_context += f"Problem: {problem_desc}\n"
                            if context_info:
                                function_context += f"Context: {context_info}\n"
                            function_context += f"Using advanced reasoning mode for this complex coding/API problem.\n\n"
                        elif func_result['function'] == 'upload_code_file':
                            # extract file upload information
                            filename = func_result['result'].get('filename', 'code.txt')
                            content = func_result['result'].get('content', '')
                            language = func_result['result'].get('language', 'java')
                            function_context += f"\n### File Upload Request:\n"
                            function_context += f"Filename: {filename}\n"
                            function_context += f"Language: {language}\n"
                            function_context += f"Content length: {len(content)} characters\n"
                            function_context += f"File will be uploaded separately.\n\n"
                        elif func_result['function'] == 'read_attachment_file':
                            res = func_result['result']
                            if res.get('success'):
                                filename = res.get('filename', 'file.txt')
                                size = res.get('size', 0)
                                content_type = res.get('content_type', '')
                                content_text = res.get('content', '')
                                preview = content_text if len(content_text) < 1200 else content_text[:1200] + "..."
                                function_context += "\n### Attachment Read:\n"
                                function_context += f"Filename: {filename} ({size} bytes, {content_type})\n"
                                function_context += f"Content Preview (trimmed):\n{preview}\n\n"
                            else:
                                function_context += f"\n### Attachment Read Failed: {res.get('error', 'Unknown error')}\n\n"
                        else:
                            function_context += f"Function {func_result['function']}: {func_result['result']}\n"
                    
                    # add function results to the prompt and generate new response
                    if think_harder_called:
                        # use advanced system prompt for complex problems (with time context)
                        advanced_with_time = self._decorate_system_prompt_with_time(self.advanced_system_prompt)
                        enhanced_prompt = (
                            advanced_with_time
                            + "\n\n"
                            + prompt
                            + function_context
                            + "\n\nBased on the additional context above, respond to the user's question. Do NOT call think_harder or fetch_more_messages again. Only call upload_code_file if you need to share code longer than 5 lines. Answer directly using the handbook context:"
                        )
                    else:
                        enhanced_prompt = prompt + function_context + "\n\nBased on the additional context above, respond to the user's question. Do NOT call any more functions - just give your response:"
                    
                    # choose model based on whether think_harder was called
                    if think_harder_called and self.model_loaded:
                        self.logger.debug("Using Gemini 2.5 Pro model for complex problem analysis")
                        # generate new response with pro model
                        new_response = await asyncio.get_event_loop().run_in_executor(
                            None, 
                            self._generate_response_sync_pro, 
                            enhanced_prompt
                        )
                        
                        # if pro model fails, fallback to regular model
                        if new_response in ["sorry, the pro model is having issues right now", "sorry, the pro model didn't return any text"]:
                            self.logger.warning("Pro model failed, falling back to regular model")
                            new_response = await asyncio.get_event_loop().run_in_executor(
                                None, 
                                self._generate_response_sync, 
                                enhanced_prompt
                            )
                    else:
                        # generate new response with regular model
                        new_response = await asyncio.get_event_loop().run_in_executor(
                            None, 
                            self._generate_response_sync, 
                            enhanced_prompt
                        )
                    
                    # check if the new response contains additional function calls (like upload_code_file)
                    self.logger.debug("Parsing function calls from enhanced response (len=%d)...", len(new_response) if new_response else 0)
                    additional_function_calls = self.function_caller.parse_function_calls(new_response)
                    if additional_function_calls:
                        self.logger.debug("Found %d additional function calls in advanced model response: %s", len(additional_function_calls), [call['name'] for call in additional_function_calls])
                        # prevent recursive think_harder loops
                        filtered_calls = [c for c in additional_function_calls if c.get('name') != 'think_harder']
                        if len(filtered_calls) != len(additional_function_calls):
                            self.logger.debug("Filtered out recursive think_harder calls from advanced step")
                        additional_function_calls = filtered_calls
                        
                        # execute additional function calls
                        for call in additional_function_calls:
                            self.logger.debug("Preparing to execute additional function '%s' with params keys: %s", call["name"], list(call.get("parameters", {}).keys()))
                            result = await self.function_caller.execute_function(call["name"], call["parameters"])
                            self.logger.debug("Additional function '%s' returned keys: %s", call["name"], list(result.keys()) if isinstance(result, dict) else [])
                            function_results.append({
                                "function": call["name"],
                                "result": result
                            })
                            executed_functions.append(call["name"])
                    
                    # remove any function calls from the new response to prevent loops
                    new_response = self.function_caller.remove_function_calls_from_text(new_response)
                    
                    # if the response is empty or just function calls, provide a fallback
                    if not new_response.strip() or new_response.strip() == "i got nothing":
                        new_response = "sorry, couldn't find any relevant context to answer that"
                    
                    # use the new response instead of the original
                    response = new_response
                else:
                    # remove function calls from response text if no results
                    response = self.function_caller.remove_function_calls_from_text(raw_response)
            else:
                # no function calls - use the raw response as-is
                response = raw_response
            
            end_time = time.time()
            response_time = (end_time - start_time) * 1000  # convert to milliseconds
            
            return response, response_time, executed_functions, function_results
        except Exception as e:
            self.logger.error(f"Error generating AI response: {e}")
            return "sorry my brain broke", 0.0, [], []

    def _generate_response_sync(self, prompt: str) -> str:
        """Synchronous response generation using Gemini 2.5 Flash Lite"""
        try:
            # Generate respon   se using Gemini 2.5 Flash Lite
            contents = [
                types.Content(
                    role="user",
                    parts=[types.Part.from_text(text=prompt)],
                ),
            ]
            
            generate_content_config = types.GenerateContentConfig(
                thinking_config=types.ThinkingConfig(thinking_budget=0),
            )
            
            # generate content using the new client
            response_chunks = []
            for chunk in self.client.models.generate_content_stream(
                model=config.AI_GEMINI_MODEL,
                contents=contents,
                config=generate_content_config,
            ):
                if chunk.text:
                    response_chunks.append(chunk.text)
            
            # combine all chunks
            full_response = ''.join(response_chunks)
            
            # debug raw response from Gemini API
            self.logger.debug("RAW GEMINI 2.5 FLASH LITE API RESPONSE (truncated to 2000 chars): %s", full_response[:2000])
            
            if full_response:
                # Preserve ne   wlines and spacing as returned by the model
                text = full_response

                # if this response contains function calls - return as-is
                if '<' in text and '{' in text:
                    self.logger.debug("FUNCTION CALL DETECTED - RETURNING RAW RESPONSE")
                    return text

                # minimal cleaning: remove timing/function-call artifacts only
                cleaned_text = text
                cleaned_text = re.sub(r'\n\n-# Took \d+ms.*?$', '', cleaned_text, flags=re.MULTILINE)
                cleaned_text = re.sub(r'-# Took \d+ms.*?$', '', cleaned_text, flags=re.MULTILINE)
                cleaned_text = re.sub(r'\n-# Took \d+ms.*?$', '', cleaned_text, flags=re.MULTILINE)
                cleaned_text = re.sub(r'\(called:.*?\)', '', cleaned_text)

                # debug cleaned response
                self.logger.debug("CLEANED RESPONSE (truncated to 2000 chars): %s", cleaned_text[:2000])

                # if we have nothing left, return a fallback
                if not cleaned_text.strip():
                    return "i got nothing"

                # enforce Discord character limit (1800 chars to be safe)
                if len(cleaned_text) > 1800:
                    trimmed = cleaned_text[:1800]
                    # prefer breaking at a newline or sentence end near the tail
                    last_break = max(trimmed.rfind('\n'), trimmed.rfind('.'))
                    if last_break > 1600:
                        cleaned_text = trimmed[:last_break + 1]
                    else:
                        cleaned_text = trimmed.rstrip() + "..."

                return cleaned_text
            else:
                return "i got nothing"

        except Exception as e:
            self.logger.error(f"Error generating AI response: {e}")
            return "sorry my brain broke"
    
    def _generate_response_sync_pro(self, prompt: str) -> str:
        """Synchronous response generation using Gemini 2.5 Flash API for complex problems"""
        try:
            # generate response using Gemini 2.5 Pro model
            contents = [
                types.Content(
                    role="user",
                    parts=[types.Part.from_text(text=prompt)],
                ),
            ]
            
            generate_content_config = types.GenerateContentConfig(
                thinking_config=types.ThinkingConfig(thinking_budget=10000),  # reasonable thinking budget
            )
            
            # generate content using the new client
            response_chunks = []
            for chunk in self.client.models.generate_content_stream(
                model=config.AI_GEMINI_PRO_MODEL,
                contents=contents,
                config=generate_content_config,
            ):
                if chunk.text:
                    response_chunks.append(chunk.text)
            
            # combine all chunks
            full_response = ''.join(response_chunks)
            
            # debug raw response from Gemini 2.5 Pro API
            self.logger.debug("RAW GEMINI 2.5 PRO API RESPONSE (truncated to 2000 chars): %s", full_response[:2000])
            
            if full_response:
                # Preserve newline  s and spacing as returned by the model
                text = full_response

                # if this response contains function calls - return as-is
                if '<' in text and '{' in text:
                    self.logger.debug("FUNCTION CALL DETECTED IN PRO MODEL - RETURNING RAW RESPONSE")
                    return text

                # Minimal cleanin   g: remove timing/function-call artifacts only
                cleaned_text = text
                cleaned_text = re.sub(r'\n\n-# Took \d+ms.*?$', '', cleaned_text, flags=re.MULTILINE)
                cleaned_text = re.sub(r'-# Took \d+ms.*?$', '', cleaned_text, flags=re.MULTILINE)
                cleaned_text = re.sub(r'\n-# Took \d+ms.*?$', '', cleaned_text, flags=re.MULTILINE)
                cleaned_text = re.sub(r'\(called:.*?\)', '', cleaned_text)

                # debug cleaned response
                self.logger.debug("CLEANED PRO MODEL RESPONSE (truncated to 2000 chars): %s", cleaned_text[:2000])

                # if we have nothing left, return a fallback
                if not cleaned_text.strip():
                    return "i got nothing"

                # enforce Discord character limit (1800 chars to be safe)
                if len(cleaned_text) > 1800:
                    trimmed = cleaned_text[:1800]
                    # prefer breaking at a newline or sentence end near the tail
                    last_break = max(trimmed.rfind('\n'), trimmed.rfind('.'))
                    if last_break > 1600:
                        cleaned_text = trimmed[:last_break + 1]
                    else:
                        cleaned_text = trimmed.rstrip() + "..."

                return cleaned_text
            else:
                return "i got nothing"

        except Exception as e:
            self.logger.error(f"Error generating AI response with 2.5 Flash model: {e}")
            return "sorry my brain broke"
    
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Handle bot mentions and generate AI responses"""
        if message.author.bot or self.bot.user not in message.mentions: 
            return
            
        question = self._clean_message_content(message.content)
        if not question: 
            return
        
        # capture a stable reference to the triggering message to avoid mis-threaded replies
        message_ref = message.to_reference(fail_if_not_exists=False)
        allowed_mentions = discord.AllowedMentions.none()

        # check if this is a reply and get the replied message
        replied_message = await self._get_replied_message(message)
        is_reply = replied_message is not None
        
        self.logger.info(f"Bot mentioned by {message.author.display_name} ({message.author.name}): {question}" + 
                        (f" (replying to message by {replied_message.author.display_name})" if is_reply else ""))
        
        async with message.channel.typing():
            recent_messages = await self._get_recent_messages(message.channel, 10, before_message=message)
            # pull auto-reply hint from AutoReplyCog if available
            system_hint: Optional[str] = None
            try:
                auto_cog = self.bot.get_cog("AutoReplyCog")
                if auto_cog and hasattr(auto_cog, "get_hint_for_message"):
                    system_hint = auto_cog.get_hint_for_message(message.content)
            except Exception as e:
                self.logger.error(f"Failed to retrieve auto-reply hint: {e}")

            prompt = self._format_context_for_gemini(recent_messages, question, message.author, replied_message, system_hint)
            # extract only the chat logs section (exclude system prompt/handbook) for logging
            try:
                marker = "\n\n### Recent Chat Context:"
                parts = prompt.split(marker, 1)
                chat_logs_for_log = (parts[1] if len(parts) > 1 else prompt).strip()
            except Exception:
                chat_logs_for_log = ""
            # Inject a small relevant handbook excerpt to ground answers
            try:
                handbook_excerpt = self._extract_relevant_handbook(question)
                if handbook_excerpt:
                    prompt = (
                        f"{prompt}\n\n### Relevant Handbook Excerpt (from experience.md):\n"
                        f"{handbook_excerpt}\n\nUse the above excerpt to answer the user's question with specific, concrete tips."
                    )
            except Exception:
                pass
            # log only the chat logs (no system preprompt)
            try:
                max_log_len = 4000
                self.logger.info("AI Mention - CHAT LOGS (truncated):\n%s", (chat_logs_for_log or "")[0:max_log_len])
            except Exception:
                pass
            response, response_time, executed_functions, function_results = await self._generate_response(prompt, message.channel.id, message.author.id)
            
        try:
            # Check if we need to uplo  ad files
            files_to_upload = []
            if function_results:
                for func_result in function_results:
                    if func_result['function'] == 'upload_code_file' and func_result['result'].get('upload_file'):
                        filename = func_result['result'].get('filename', 'code.txt')
                        content = func_result['result'].get('content', '')
                        language = func_result['result'].get('language', 'java')
                        
                        # Create a file-like object
                        import io
                        files_to_upload.append(discord.File(io.BytesIO(content.encode('utf-8')), filename=filename))
            
            # add timing information, token usage, and function calls to the response
            timing_info = f"-# Took {response_time:.0f}ms"

            # determine which model likely generated the final response
            try:
                model_used = config.AI_GEMINI_PRO_MODEL if (executed_functions and any(fn == "think_harder" for fn in executed_functions)) else config.AI_GEMINI_MODEL
                # compute token usage (prompt + completion) with graceful fallbacks
                prompt_tokens, prompt_method = self._count_tokens_for_model_with_method(model_used, prompt)
                completion_tokens, completion_method = self._count_tokens_for_model_with_method(model_used, response)
                total_tokens = prompt_tokens + completion_tokens
                method_tag = 'sdk' if prompt_method == completion_method == 'sdk' else ('est' if prompt_method == completion_method == 'est' else 'mixed')
                max_ctx = self._get_model_context_window(model_used)
                if max_ctx and isinstance(max_ctx, int) and max_ctx > 0:
                    timing_info += f" | tokens {total_tokens:,}/{max_ctx:,} ({method_tag})"
                else:
                    timing_info += f" | tokens {total_tokens:,} ({method_tag})"
            except Exception:
                # if token accounting fails, we keep timing only
                pass
            if executed_functions:
                timing_info += f" (called: {', '.join(executed_functions)})"

            # log the response alongside the timing/footer for debugging
            try:
                self.logger.info(
                    "AI Mention - MODEL RESPONSE (ms=%d, truncated):\n%s",
                    int(response_time),
                    (response or "")[0:4000]
                )
            except Exception:
                pass

            # if files are being uploaded, include a concise caption and the model's commentary
            if files_to_upload:
                # prefer the first file's name for a concise caption
                primary_filename = None
                for func_result in function_results:
                    if func_result['function'] == 'upload_code_file' and func_result['result'].get('upload_file'):
                        primary_filename = func_result['result'].get('filename')
                        break
                caption = "Uploaded code file."
                if primary_filename:
                    caption = f"Uploaded code file: {primary_filename}"
                # combine caption with the AI's commentary
                combined_text = f"{caption}\n\n{response}".strip()
                # enforce character limit allowing room for timing_info
                max_len = 1800 - (len(timing_info) + 2)
                if len(combined_text) > max_len:
                    trimmed = combined_text[:max_len]
                    last_period = trimmed.rfind('.')
                    if last_period > max_len - 200:
                        combined_text = trimmed[:last_period + 1]
                    else:
                        combined_text = trimmed.rstrip() + "..."
                full_response = f"{combined_text}\n\n{timing_info}"
                await message.channel.send(full_response, reference=message_ref, files=files_to_upload, allowed_mentions=allowed_mentions)
            else:
                # combine AI commentary
                combined_text = (response or "").strip()
                # enforce character limit allowing room for timing_info
                max_len = 1800 - (len(timing_info) + 2)
                if len(combined_text) > max_len:
                    trimmed = combined_text[:max_len]
                    last_period = trimmed.rfind('.')
                    if last_period > max_len - 200:
                        combined_text = trimmed[:last_period + 1]
                    else:
                        combined_text = trimmed.rstrip() + "..."
                full_response = f"{combined_text}\n\n{timing_info}"
                await message.channel.send(full_response, reference=message_ref, allowed_mentions=allowed_mentions)
        except discord.HTTPException as e:
            self.logger.error(f"Failed to send AI response: {e}")

    async def cog_unload(self):
        """Clean up resources when cog is unloaded"""
        super().cog_unload()

async def setup(bot: commands.Bot):
    """Setup function for the AI mention cog"""
    await bot.add_cog(AIMentionCog(bot))
