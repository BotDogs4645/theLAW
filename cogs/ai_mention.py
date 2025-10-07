import discord
from discord.ext import commands
from utils.cog_base import BaseCog
from utils import logger, function_caller, prompt_loader
import asyncio
import re
import time
from datetime import datetime
import io
from typing import List, Dict, Optional, Tuple, Set, Any

from google import genai
from google.genai import types
import config


class AIMentionCog(BaseCog):
    """Responds to @mentions using Gemini with tool-calling and escalation."""

    def __init__(self, bot: commands.Bot):
        super().__init__(bot)
        self.client: Optional[genai.Client] = None
        self.model_loaded = False
        self.model_loading = False
        self.function_caller = function_caller.FunctionCaller(bot)

    async def cog_load(self):
        super().cog_load()
        await self._initialize_genai()

    async def _initialize_genai(self):
        if self.model_loading or self.model_loaded:
            return
        self.model_loading = True
        try:
            self.client = genai.Client(api_key=config.AI_GEMINI_API_KEY)
            self.model_loaded = True
            self.logger.info("Initialized google-genai client")
        except Exception as e:
            self.logger.error(f"Failed to init GenAI: {e}", exc_info=True)
        finally:
            self.model_loading = False

    def _clean_message_content(self, content: str) -> str:
        content = re.sub(r'<@!?\d+>', '', content).strip()
        return ' '.join(content.split())

    async def _get_recent_messages(self, channel: discord.TextChannel, *, limit: int = 5, before: Optional[discord.Message] = None) -> List[discord.Message]:
        messages: List[discord.Message] = []
        async for msg in channel.history(limit=limit, before=before):
            messages.append(msg)
        return list(reversed(messages))

    def _current_time_str(self) -> str:
        return datetime.now().isoformat(timespec='seconds')

    def _format_author_tag(self, member: discord.abc.User) -> str:
        username = getattr(member, 'name', 'unknown')
        display = getattr(member, 'display_name', username)
        return f"@{username} | {display}"

    def _build_system_prompt(self, *, pro: bool) -> str:
        base = prompt_loader.load_advanced_model_prompt() if pro else prompt_loader.load_lite_model_prompt()
        now = self._current_time_str()
        if pro:
            guidelines = (
                "Format: Do not prepend speaker tags or names; reply in plain text. "
                "Attribution: Mention names only if asked or quoting content. "
                "Tool policy: Prefer answering directly. Do NOT call 'think_harder' in pro mode. "
                "Follow-ups: If a prior tool response contains the needed data, answer from that context without calling more tools. "
                "Schedules: When a schedule tool returns an object with fields (e.g., teachers, room, time), use those fields to answer follow-up questions like 'who is teaching?'. "
            )
        else:
            guidelines = (
                "Format: Do not prepend speaker tags or names; reply in plain text. "
                "Attribution: Mention names only if asked or quoting content. "
                "Tool policy: Prefer answering directly. Escalate with 'think_harder' for implementation, debugging, or engineering calculations. "
                "Follow-ups: If a prior tool response contains the needed data, answer from that context without calling more tools. "
                "Schedules: When a schedule tool returns an object with fields (e.g., teachers, room, time), use those fields to answer follow-up questions like 'who is teaching?'. "
            )
        return f"{base}\n\nCurrent datetime: {now}\n\n{guidelines}"

    def _build_generation_config(self, *, pro: bool, tool_mode: str = 'ANY', allow_functions: Optional[Set[str]] = None) -> types.GenerateContentConfig:
        tools = self.function_caller.get_tool_config(include=allow_functions) if allow_functions else self.function_caller.get_tool_config()
        return types.GenerateContentConfig(
            system_instruction=self._build_system_prompt(pro=pro),
            tools=tools,
            tool_config=types.ToolConfig(
                function_calling_config=types.FunctionCallingConfig(mode=tool_mode)
            ),
            temperature=(config.AI_TEMPERATURE_PRO if pro else config.AI_TEMPERATURE),
            top_p=(config.AI_TOP_P_PRO if pro else config.AI_TOP_P),
            max_output_tokens=(config.AI_MAX_TOKENS_PRO if pro else config.AI_MAX_TOKENS),
        )

    def _build_contents(self, history: List[discord.Message], asker: discord.Member, question: str) -> List[types.Content]:
        contents: List[types.Content] = []
        for msg in history:
            text = self._clean_message_content(msg.content)
            if not text:
                continue
            if msg.author.id == self.bot.user.id:
                # for prior bot messages, include only the content to avoid teaching a prefix format
                contents.append(types.Content(role='model', parts=[types.Part(text=text)]))
            else:
                username = getattr(msg.author, 'name', 'unknown')
                display = getattr(msg.author, 'display_name', username)
                contents.append(types.Content(role='user', parts=[types.Part(text=f"{display} (@{username}): {text}")]))
        username = getattr(asker, 'name', 'unknown')
        display = getattr(asker, 'display_name', username)
        contents.append(types.Content(role='user', parts=[types.Part(text=f"{display} (@{username}): {question}")]))
        return contents

    async def _run_generation_with_tools(self, *, contents: List[types.Content], pro: bool, tool_mode: str = 'ANY', allow_functions: Optional[Set[str]] = None, context: Optional[Dict[str, Any]] = None) -> Tuple[str, float, List[str], List[Dict[str, dict]], bool]:
        if not self.model_loaded or not self.client:
            return "My brain is still starting up. Try again in a moment.", 0.0, [], [], False

        start = time.time()
        executed: List[str] = []
        results: List[Dict[str, dict]] = []
        escalate_to_pro = False
        upload_done = False
        think_harder_called = False

        model_name = f"models/{config.AI_GEMINI_PRO_MODEL if pro else config.AI_GEMINI_MODEL}"
        cfg = self._build_generation_config(pro=pro, tool_mode=tool_mode, allow_functions=allow_functions)

        try:
            response = await self.client.aio.models.generate_content(
                model=model_name,
                contents=contents,
                config=cfg
            )

            max_tool_calls = 6
            tool_calls = 0

            while (
                getattr(response, 'candidates', None)
                and response.candidates
                and getattr(response.candidates[0], 'content', None)
                and any(getattr(p, 'function_call', None) for p in (getattr(response.candidates[0].content, 'parts', None) or []))
            ):
                if tool_calls >= max_tool_calls:
                    self.logger.warning("Max tool calls reached; breaking loop")
                    break
                tool_calls += 1

                if tool_mode == 'NONE':
                    break

                # if lite model requests think_harder, escalate immediately without executing loops
                if not pro and any(
                    getattr(p, 'function_call', None) and getattr(getattr(p, 'function_call', None), 'name', '') == 'think_harder'
                    for p in (getattr(response.candidates[0].content, 'parts', None) or [])
                ):
                    escalate_to_pro = True
                    break

                contents.append(response.candidates[0].content)

                tool_response_parts: List[types.Part] = []
                for part in (getattr(response.candidates[0].content, 'parts', None) or []):
                    if not part.function_call:
                        continue
                    call = part.function_call
                    params = dict(call.args) if call.args else {}
                    if call.name == 'upload_code_file':
                        # block uploads in lite mode
                        if not pro:
                            suppressed = {
                                "success": False,
                                "error": "Upload suppressed in lite mode; answer inline or escalate.",
                                "upload_file": False
                            }
                            tool_response_parts.append(
                                types.Part(function_response=types.FunctionResponse(name=call.name, response=suppressed))
                            )
                            executed.append(call.name)
                            results.append({"function": call.name, "result": suppressed})
                            continue
                        # only allow one upload per turn
                        if upload_done:
                            suppressed = {
                                "success": False,
                                "error": "Duplicate upload suppressed; limit one upload per interaction.",
                                "upload_file": False
                            }
                            tool_response_parts.append(
                                types.Part(function_response=types.FunctionResponse(name=call.name, response=suppressed))
                            )
                            executed.append(call.name)
                            results.append({"function": call.name, "result": suppressed})
                            continue
                        # large enough and code-like, not markdown/prose
                        filename = str(params.get('filename', ''))
                        content = str(params.get('content', ''))
                        language = str(params.get('language', '')).lower()
                        too_short = len(content) < 2000 and content.count('\n') < 100
                        is_markdownish = language in {'markdown', 'md'} or filename.endswith('.md') or filename.endswith('.txt')
                        looks_like_code = any(token in content for token in ['class ', 'public ', 'private ', ';', '{', '}', 'def ', 'import ', 'package ']) or content.strip().startswith('```')
                        if too_short or is_markdownish or not looks_like_code:
                            suppressed = {
                                "success": False,
                                "error": "Upload rejected: only large source code files are allowed (no markdown/prose).",
                                "upload_file": False
                            }
                            tool_response_parts.append(
                                types.Part(function_response=types.FunctionResponse(name=call.name, response=suppressed))
                            )
                            executed.append(call.name)
                            results.append({"function": call.name, "result": suppressed})
                            continue
                    if call.name == 'think_harder':
                        # block think_harder in pro mode
                        if pro:
                            suppressed = {
                                "success": False,
                                "error": "think_harder is not allowed in pro mode.",
                            }
                            tool_response_parts.append(
                                types.Part(function_response=types.FunctionResponse(name=call.name, response=suppressed))
                            )
                            executed.append(call.name)
                            results.append({"function": call.name, "result": suppressed})
                            continue
                        if think_harder_called:
                            suppressed = {
                                "success": False,
                                "error": "Duplicate think_harder call suppressed; only once per interaction.",
                            }
                            tool_response_parts.append(
                                types.Part(function_response=types.FunctionResponse(name=call.name, response=suppressed))
                            )
                            executed.append(call.name)
                            results.append({"function": call.name, "result": suppressed})
                            continue
                    result = await self.function_caller.execute_function(call.name, params, _context=context)

                    executed.append(call.name)
                    results.append({"function": call.name, "result": result})

                    if call.name == "think_harder" and not pro:
                        escalate_to_pro = True

                    tool_response_parts.append(
                        types.Part(function_response=types.FunctionResponse(name=call.name, response=result))
                    )
                    if call.name == 'upload_code_file' and result and isinstance(result, dict) and result.get('success') and result.get('upload_file'):
                        upload_done = True
                    if call.name == 'think_harder' and (result and isinstance(result, dict) and result.get('success')):
                        think_harder_called = True

                contents.append(types.Content(role='tool', parts=tool_response_parts))

                # if escalation somehow requested by a tool result, break and re-run with pro
                if escalate_to_pro and not pro:
                    break

                response = await self.client.aio.models.generate_content(
                    model=model_name,
                    contents=contents,
                    config=cfg
                )

            elapsed_ms = (time.time() - start) * 1000
            text = response.text if hasattr(response, 'text') else None

            # if we still have no text, force a final answer without tools
            if not (text and text.strip()):
                contents.append(types.Content(role='user', parts=[
                    types.Part(text="Using the tool results above, answer the user's request concisely. Do not call any tools.")
                ]))
                cfg_final = self._build_generation_config(pro=pro, tool_mode='NONE')
                try:
                    response = await self.client.aio.models.generate_content(
                        model=model_name,
                        contents=contents,
                        config=cfg_final
                    )
                    text = response.text if hasattr(response, 'text') else text
                except Exception as _:
                    pass

            return (text or ""), elapsed_ms, executed, results, escalate_to_pro
        except Exception as e:
            self.logger.error(f"GenAI generation failed: {e}", exc_info=True)
            return "Sorry, I hit an error while thinking.", 0.0, [], [], False

    async def _maybe_handle_uploads(self, message: discord.Message, function_results: List[Dict[str, dict]]):
        seen: Set[Tuple[str, int]] = set()
        for item in function_results:
            res = item.get("result") or {}
            if isinstance(res, dict) and res.get("upload_file") and res.get("success"):
                filename = res.get("filename", "code.txt")
                content = res.get("content", "")
                sig = (filename, hash(content))
                if sig in seen:
                    continue
                seen.add(sig)
                buf = io.BytesIO(content.encode("utf-8"))
                file = discord.File(fp=buf, filename=filename)
                await message.reply(content=res.get("message", "Here is the file."), file=file, mention_author=False)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        if not self.bot.user or self.bot.user not in message.mentions:
            return

        question = self._clean_message_content(message.content)
        if not question:
            return

        async with message.channel.typing():
            history = await self._get_recent_messages(message.channel, limit=5, before=message)
            contents = self._build_contents(history, message.author, question)

            # build execution context for tool calls
            exec_context: Dict[str, Any] = {
                "channel_id": getattr(getattr(message, "channel", None), "id", None),
                "guild_id": getattr(getattr(message, "guild", None), "id", None),
                "author_id": getattr(getattr(message, "author", None), "id", None),
                "message_id": getattr(message, "id", None),
                "last_user_text": question,
            }

            # try with lite model using auto tool-calling
            allowed_lite: Set[str] = {
                'think_harder', 'read_attachment_file',
                'get_schedule_today', 'get_schedule_date', 'get_next_meeting', 'find_meeting', 'get_meeting_notes'
            }
            text, _, executed, results, want_pro = await self._run_generation_with_tools(
                contents=contents.copy(), pro=False, tool_mode='AUTO', allow_functions=allowed_lite, context=exec_context
            )

            # if escalation requested or the question clearly implies implementation, re-run with pro
            implementation_keywords = [
                'pid', 'sparkmax', 'cansparkmax', 'neo', 'talonfx', 'falcon', 'swerve', 'subsystem', 'command', 'pidcontroller'
            ]
            needs_impl = any(k in question.lower() for k in implementation_keywords)
            if want_pro or needs_impl:
                text, _, executed2, results2, _ = await self._run_generation_with_tools(contents=contents.copy(), pro=True, tool_mode='ANY', context=exec_context)
                executed.extend(executed2)
                results.extend(results2)

        if text:
            await message.reply(text, mention_author=False)
            # handle any post-response effects
            await self._maybe_handle_uploads(message, results)


async def setup(bot: commands.Bot):
    await bot.add_cog(AIMentionCog(bot))
