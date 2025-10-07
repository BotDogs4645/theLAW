import discord
from discord import app_commands
from discord.ext import commands
from utils.cog_base import BaseCog, slash_admin_only
from utils import logger, function_caller, prompt_loader, database
import asyncio
import re
import time
from datetime import datetime
import io
import json
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
                "No fabrication: Never invent schedules, names, links, or data. If unknown, say so. "
                "Greetings: If the user only greets (e.g., 'hello'), reply briefly; do not call tools or introduce schedules. "
                "Schedules: Only discuss schedules if explicitly requested or provided by a tool in this interaction; otherwise, do not mention them. "
                "Intent: Do not infer intent from keywords; respond to the explicit request only. "
            )
        else:
            guidelines = (
                "Format: Do not prepend speaker tags or names; reply in plain text. "
                "Attribution: Mention names only if asked or quoting content. "
                "Tool policy: Prefer answering directly. Escalate with 'think_harder' for implementation, debugging, or engineering calculations. "
                "Follow-ups: If a prior tool response contains the needed data, answer from that context without calling more tools. "
                "No fabrication: Never invent schedules, names, links, or data. If unknown, say so. "
                "Greetings: If the user only greets (e.g., 'hello'), reply briefly; do not call tools, escalate, or introduce schedules. "
                "Schedules: Only call schedule tools when explicitly asked; otherwise do not mention schedules. "
                "Intent: Do not infer intent from keywords; respond to the explicit request only. "
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

    def _json_dumps_safe(self, data: Any) -> str:
        try:
            return json.dumps(data, ensure_ascii=False, default=str)
        except Exception:
            return str(data)

    async def _run_generation_with_tools(self, *, contents: List[types.Content], pro: bool, tool_mode: str = 'ANY', allow_functions: Optional[Set[str]] = None, context: Optional[Dict[str, Any]] = None, interaction_id: Optional[int] = None, function_seq_start: int = 0) -> Tuple[str, float, List[str], List[Dict[str, dict]], bool, float, int, str]:
        if not self.model_loaded or not self.client:
            return "My brain is still starting up. Try again in a moment.", 0.0, [], [], False, 0.0, 0, ""

        start = time.time()
        executed: List[str] = []
        results: List[Dict[str, dict]] = []
        escalate_to_pro = False
        upload_done = False
        think_harder_called = False
        gemini_total_ms: float = 0.0
        function_calls_logged: int = 0
        function_seq_index: int = int(function_seq_start or 0)

        model_name = f"models/{config.AI_GEMINI_PRO_MODEL if pro else config.AI_GEMINI_MODEL}"
        cfg = self._build_generation_config(pro=pro, tool_mode=tool_mode, allow_functions=allow_functions)

        try:
            _gem_start = time.time()
            response = await self.client.aio.models.generate_content(
                model=model_name,
                contents=contents,
                config=cfg
            )
            _gem_ms = (time.time() - _gem_start) * 1000
            gemini_total_ms += _gem_ms
            try:
                if interaction_id:
                    database.log_ai_gemini_call(
                        interaction_id,
                        model_name=model_name,
                        tool_mode=str(tool_mode),
                        allow_functions_json=self._json_dumps_safe(sorted(list(allow_functions)) if allow_functions else []),
                        started_at=datetime.utcnow().isoformat(),
                        elapsed_ms=_gem_ms,
                    )
            except Exception:
                pass

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
                    _fn_started_at_iso = datetime.utcnow().isoformat()
                    _fn_start_time = time.time()
                    result = await self.function_caller.execute_function(call.name, params, _context=context)
                    _fn_ms = (time.time() - _fn_start_time) * 1000
                    try:
                        if interaction_id:
                            database.log_ai_function_call(
                                interaction_id,
                                sequence_index=function_seq_index,
                                function_name=call.name,
                                params_json=self._json_dumps_safe(params),
                                result_json=self._json_dumps_safe(result),
                                started_at=_fn_started_at_iso,
                                elapsed_ms=_fn_ms,
                            )
                            function_calls_logged += 1
                            function_seq_index += 1
                    except Exception:
                        pass

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

                _gem_start = time.time()
                response = await self.client.aio.models.generate_content(
                    model=model_name,
                    contents=contents,
                    config=cfg
                )
                _gem_ms = (time.time() - _gem_start) * 1000
                gemini_total_ms += _gem_ms
                try:
                    if interaction_id:
                        database.log_ai_gemini_call(
                            interaction_id,
                            model_name=model_name,
                            tool_mode=str(tool_mode),
                            allow_functions_json=self._json_dumps_safe(sorted(list(allow_functions)) if allow_functions else []),
                            started_at=datetime.utcnow().isoformat(),
                            elapsed_ms=_gem_ms,
                        )
                except Exception:
                    pass

            elapsed_ms = (time.time() - start) * 1000
            text = response.text if hasattr(response, 'text') else None

            # if we still have no text, force a final answer without tools
            if not (text and text.strip()):
                contents.append(types.Content(role='user', parts=[
                    types.Part(text="Using the tool results above, answer the user's request concisely. Do not call any tools.")
                ]))
                cfg_final = self._build_generation_config(pro=pro, tool_mode='NONE')
                try:
                    _gem_start = time.time()
                    response = await self.client.aio.models.generate_content(
                        model=model_name,
                        contents=contents,
                        config=cfg_final
                    )
                    _gem_ms = (time.time() - _gem_start) * 1000
                    gemini_total_ms += _gem_ms
                    try:
                        if interaction_id:
                            database.log_ai_gemini_call(
                                interaction_id,
                                model_name=model_name,
                                tool_mode='NONE',
                                allow_functions_json=self._json_dumps_safe(sorted(list(allow_functions)) if allow_functions else []),
                                started_at=datetime.utcnow().isoformat(),
                                elapsed_ms=_gem_ms,
                            )
                    except Exception:
                        pass
                    text = response.text if hasattr(response, 'text') else text
                except Exception as _:
                    pass

            return (text or ""), elapsed_ms, executed, results, escalate_to_pro, gemini_total_ms, function_calls_logged, model_name
        except Exception as e:
            self.logger.error(f"GenAI generation failed: {e}", exc_info=True)
            return "Sorry, I hit an error while thinking.", 0.0, [], [], False, 0.0, 0, model_name

    async def _maybe_handle_uploads(self, message: discord.Message, function_results: List[Dict[str, dict]], *, interaction_id: Optional[int] = None):
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
                _started_at_iso = datetime.utcnow().isoformat()
                _start = time.time()
                await message.reply(content=res.get("message", "Here is the file."), file=file, mention_author=False)
                _ms = (time.time() - _start) * 1000
                try:
                    if interaction_id:
                        database.log_ai_discord_step(
                            interaction_id,
                            step_name="upload_file",
                            started_at=_started_at_iso,
                            elapsed_ms=_ms,
                            extra_json=self._json_dumps_safe({"filename": filename, "size": len(content)})
                        )
                except Exception:
                    pass

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
            total_started_at = time.time()
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

            # create chat history json for logging
            chat_history_data = []
            for msg in history:
                try:
                    chat_history_data.append({
                        "id": getattr(msg, "id", None),
                        "author_id": getattr(getattr(msg, "author", None), "id", None),
                        "author": getattr(getattr(msg, "author", None), "display_name", None) or getattr(getattr(msg, "author", None), "name", None),
                        "is_bot": bool(getattr(getattr(msg, "author", None), "bot", False)),
                        "content": self._clean_message_content(getattr(msg, "content", ""))
                    })
                except Exception:
                    pass
            chat_history_json = self._json_dumps_safe(chat_history_data)

            # start DB interaction log
            interaction_id = None
            try:
                interaction_id = database.start_ai_interaction(
                    guild_id=exec_context.get("guild_id"),
                    channel_id=exec_context.get("channel_id"),
                    author_id=exec_context.get("author_id"),
                    message_id=exec_context.get("message_id"),
                    question=question,
                    chat_history_json=chat_history_json,
                )
            except Exception:
                interaction_id = None

            # try with lite model using auto tool-calling
            allowed_lite: Set[str] = {
                'think_harder', 'read_attachment_file',
                'get_schedule_today', 'get_schedule_date', 'get_next_meeting', 'find_meeting', 'get_meeting_notes'
            }
            text, _, executed, results, want_pro, gem_ms_1, fn_calls_1, model_name_1 = await self._run_generation_with_tools(
                contents=contents.copy(), pro=False, tool_mode='AUTO', allow_functions=allowed_lite, context=exec_context, interaction_id=interaction_id, function_seq_start=0
            )

            # if escalation requested by the model, re-run with pro
            gem_ms_total = gem_ms_1
            fn_calls_total = fn_calls_1
            model_name_final = model_name_1
            pro_final = False
            if want_pro:
                text, _, executed2, results2, _, gem_ms_2, fn_calls_2, model_name_2 = await self._run_generation_with_tools(contents=contents.copy(), pro=True, tool_mode='ANY', context=exec_context, interaction_id=interaction_id, function_seq_start=fn_calls_total)
                executed.extend(executed2)
                results.extend(results2)
                gem_ms_total += gem_ms_2
                fn_calls_total += fn_calls_2
                model_name_final = model_name_2
                pro_final = True

        if text:
            _discord_started_at_iso = datetime.utcnow().isoformat()
            _discord_start = time.time()
            await message.reply(text, mention_author=False)
            discord_reply_ms = (time.time() - _discord_start) * 1000
            try:
                if interaction_id:
                    database.log_ai_discord_step(
                        interaction_id,
                        step_name="send_reply",
                        started_at=_discord_started_at_iso,
                        elapsed_ms=discord_reply_ms,
                    )
            except Exception:
                pass
            # handle any post-response effects
            await self._maybe_handle_uploads(message, results, interaction_id=interaction_id)
            total_elapsed_ms = (time.time() - total_started_at) * 1000
            try:
                if interaction_id:
                    database.complete_ai_interaction(
                        interaction_id,
                        pro_mode=pro_final,
                        model_name=model_name_final,
                        response_text=text,
                        total_elapsed_ms=total_elapsed_ms,
                        gemini_total_ms=gem_ms_total,
                        discord_reply_ms=discord_reply_ms,
                        tool_calls_count=len([e for e in executed if e])
                    )
            except Exception:
                pass


    def _parse_message_id_or_link(self, value: Optional[str]) -> Optional[int]:
        if not value:
            return None
        value = value.strip()
        if value.isdigit():
            try:
                return int(value)
            except Exception:
                return None
        # attempt to parse discord message link
        try:
            parts = value.split('/')
            if len(parts) >= 3:
                maybe_id = parts[-1]
                if maybe_id.isdigit():
                    return int(maybe_id)
        except Exception:
            pass
        return None

    def _build_inspection_report(self, interaction_row: dict, gemini_calls: list, function_calls: list, discord_steps: list) -> str:
        lines: List[str] = []
        iid = interaction_row.get('id')
        lines.append(f"AI Interaction #{iid}")
        lines.append("Context:")
        lines.append(f"  created_at    : {interaction_row.get('created_at')}")
        lines.append(f"  guild_id      : {interaction_row.get('guild_id')}")
        lines.append(f"  channel_id    : {interaction_row.get('channel_id')}")
        lines.append(f"  author_id     : {interaction_row.get('author_id')}")
        lines.append(f"  message_id    : {interaction_row.get('message_id')}")
        lines.append("")
        q = interaction_row.get('question') or ''
        r = interaction_row.get('response_text') or ''
        q_tr = q if len(q) <= 800 else q[:797] + '...'
        r_tr = r if len(r) <= 800 else r[:797] + '...'
        lines.append("Conversation:")
        lines.append(f"  Question      : {q_tr}")
        lines.append(f"  Response (tr) : {r_tr}")
        lines.append("")
        lines.append("Totals:")
        lines.append(f"  pro_mode      : {bool(interaction_row.get('pro_mode'))}")
        lines.append(f"  model_name    : {interaction_row.get('model_name')}")
        lines.append(f"  tool_calls    : {interaction_row.get('tool_calls_count')}")
        lines.append(f"  gemini_total  : {interaction_row.get('gemini_total_ms')} ms")
        lines.append(f"  discord_reply : {interaction_row.get('discord_reply_ms')} ms")
        lines.append(f"  total_elapsed : {interaction_row.get('total_elapsed_ms')} ms")
        lines.append("")
        lines.append(f"Gemini calls ({len(gemini_calls)}):")
        if gemini_calls:
            for i, call in enumerate(gemini_calls, start=1):
                allow = []
                try:
                    allow = json.loads(call.get('allow_functions_json') or '[]')
                except Exception:
                    pass
                lines.append(f"  [{i:02d}] {call.get('elapsed_ms')} ms | {call.get('model_name')} | tool_mode={call.get('tool_mode')} | allow={allow}")
        else:
            lines.append("  (none)")
        lines.append("")
        lines.append(f"Function calls ({len(function_calls)}):")
        if function_calls:
            for fc in function_calls:
                seq = fc.get('sequence_index')
                name = fc.get('function_name')
                ms = fc.get('elapsed_ms')
                params = fc.get('params_json')
                result = fc.get('result_json')
                try:
                    params_obj = json.loads(params) if params else None
                except Exception:
                    params_obj = params
                try:
                    result_obj = json.loads(result) if result else None
                except Exception:
                    result_obj = result
                params_text = json.dumps(params_obj, ensure_ascii=False, indent=2, default=str) if params_obj is not None else ''
                result_text = json.dumps(result_obj, ensure_ascii=False, indent=2, default=str) if result_obj is not None else ''
                if len(params_text) > 600: params_text = params_text[:597] + '...'
                if len(result_text) > 600: result_text = result_text[:597] + '...'
                lines.append(f"  - [{seq}] {name} | {ms} ms")
                if params_text:
                    for ln in params_text.splitlines():
                        lines.append(f"      params : {ln}" if ln else "      params :")
                if result_text:
                    for ln in result_text.splitlines():
                        lines.append(f"      result : {ln}" if ln else "      result :")
        else:
            lines.append("  (none)")
        lines.append("")
        lines.append(f"Discord steps ({len(discord_steps)}):")
        if discord_steps:
            for ds in discord_steps:
                name = ds.get('step_name')
                ms = ds.get('elapsed_ms')
                extra = ds.get('extra_json')
                try:
                    extra_obj = json.loads(extra) if extra else None
                except Exception:
                    extra_obj = extra
                extra_text = json.dumps(extra_obj, ensure_ascii=False, indent=2, default=str) if extra_obj is not None else ''
                if len(extra_text) > 400: extra_text = extra_text[:397] + '...'
                lines.append(f"  - {name} | {ms} ms")
                if extra_text:
                    for ln in extra_text.splitlines():
                        lines.append(f"      extra  : {ln}" if ln else "      extra  :")
        else:
            lines.append("  (none)")
        return "\n".join(lines)

    async def _send_long_ephemeral(self, interaction: discord.Interaction, text: str):
        # split into <=1900 char chunks, wrap in code blocks per chunk for readability
        max_len = 1900
        chunks: List[str] = []
        current = []
        current_len = 0
        for line in text.splitlines():
            add_len = len(line) + 1
            if current_len + add_len > max_len:
                chunks.append("\n".join(current))
                current = [line]
                current_len = len(line) + 1
            else:
                current.append(line)
                current_len += add_len
        if current:
            chunks.append("\n".join(current))

        # send first response
        if not interaction.response.is_done():
            await interaction.response.send_message(f"```\n{chunks[0]}\n```", ephemeral=True)
        else:
            await interaction.followup.send(f"```\n{chunks[0]}\n```", ephemeral=True)
        # followups
        for chunk in chunks[1:]:
            await interaction.followup.send(f"```\n{chunk}\n```", ephemeral=True)

    @app_commands.command(name="inspect_ai", description="Admin-only: inspect AI interaction by message ID or latest reply context")
    @slash_admin_only()
    async def inspect_ai(self, interaction: discord.Interaction, message_id: Optional[str] = None):
        await interaction.response.defer(ephemeral=True, thinking=True)

        channel = interaction.channel
        if not isinstance(channel, discord.TextChannel):
            await interaction.followup.send("Run this in a text channel.", ephemeral=True)
            return

        target_message_id: Optional[int] = self._parse_message_id_or_link(message_id)

        # if provided message_id refers to a reply, use its referenced message id
        if target_message_id:
            try:
                msg = await channel.fetch_message(target_message_id)
                if getattr(msg, 'reference', None) and getattr(msg.reference, 'message_id', None):
                    target_message_id = int(msg.reference.message_id)
            except Exception:
                pass

        # if not provided, try to infer from the latest bot reply in this channel
        if not target_message_id:
            try:
                async for m in channel.history(limit=50):
                    if m.author.id == self.bot.user.id and getattr(m, 'reference', None) and getattr(m.reference, 'message_id', None):
                        target_message_id = int(m.reference.message_id)
                        break
            except Exception:
                pass

        if not target_message_id:
            await interaction.followup.send("Could not infer a message ID. Provide one or run in a channel with a recent bot reply.", ephemeral=True)
            return

        # find interaction by message_id
        with database.get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM ai_interactions WHERE message_id = ? ORDER BY id DESC LIMIT 1", (target_message_id,))
            row = cur.fetchone()

        if not row:
            await interaction.followup.send(f"No AI interaction found for message_id={target_message_id}", ephemeral=True)
            return

        interaction_row = dict(row)
        interaction_id = interaction_row.get('id')

        with database.get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM ai_gemini_calls WHERE interaction_id = ? ORDER BY id ASC", (interaction_id,))
            gemini_calls = [dict(r) for r in cur.fetchall()]
            cur.execute("SELECT * FROM ai_function_calls WHERE interaction_id = ? ORDER BY sequence_index ASC, id ASC", (interaction_id,))
            function_calls = [dict(r) for r in cur.fetchall()]
            cur.execute("SELECT * FROM ai_discord_steps WHERE interaction_id = ? ORDER BY id ASC", (interaction_id,))
            discord_steps = [dict(r) for r in cur.fetchall()]

        report = self._build_inspection_report(interaction_row, gemini_calls, function_calls, discord_steps)
        await self._send_long_ephemeral(interaction, report)


async def setup(bot: commands.Bot):
    await bot.add_cog(AIMentionCog(bot))
