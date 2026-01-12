import discord
from discord import app_commands
from discord.ext import commands
from utils.cog_base import BaseCog, slash_admin_only
from utils import logger, function_caller, prompt_loader, ai_conversation
from utils.db import start_ai_interaction, complete_ai_interaction, get_db_connection
import asyncio
import time
import io
import json
from typing import List, Dict, Optional, Any, Set, Tuple

from openai import AsyncOpenAI
import config


class AIMentionCog(BaseCog):
    """
    Responds to @mentions using the modern OpenAI tool-calling API and a
    lite/pro model escalation system.
    """

    def __init__(self, bot: commands.Bot):
        super().__init__(bot)
        # Use AsyncOpenAI for non-blocking requests.
        self.client: Optional[AsyncOpenAI] = None
        self.function_caller = function_caller.FunctionCaller(bot)

    async def cog_load(self):
        """Initializes the cog and the AsyncOpenAI client."""
        super().cog_load()
        if config.AI_OPENAI_API_KEY:
            self.client = AsyncOpenAI(api_key=config.AI_OPENAI_API_KEY)
            self.logger.info("Initialized AsyncOpenAI client.")
        else:
            self.logger.warning("AI_OPENAI_API_KEY is not set. AI features will be disabled.")

    async def _get_recent_messages(self, channel: discord.TextChannel, *, limit: int = 5,
                                   before: Optional[discord.Message] = None) -> List[discord.Message]:
        """Fetches a brief history of messages from a channel."""
        msgs: List[discord.Message] = [m async for m in channel.history(limit=limit, before=before)]
        return list(reversed(msgs))

    async def _run_conversation_loop(
            self,
            messages: List[Dict[str, Any]],
            pro: bool,
            allowed_functions: Optional[Set[str]],
            context: Dict[str, Any]
    ) -> Tuple[str, float, List[Dict[str, Any]], bool]:
        """
        Runs the main conversation loop with the OpenAI model, handling tool calls.
        """
        if not self.client:
            return "My AI brain is not configured.", 0.0, [], False

        loop_start_time = time.time()
        executed_tools: List[Dict[str, Any]] = []
        wants_escalation = False
        max_tool_cycles = config.MAX_TOOL_CYCLES

        model_name = config.AI_OPENAI_PRO_MODEL if pro else config.AI_OPENAI_MODEL
        tools = self.function_caller.get_openai_tools(include=allowed_functions)

        # The conversation loop for handling multi-step tool calls
        for i in range(max_tool_cycles):
            try:
                response = await self.client.chat.completions.create(
                    model=model_name,
                    messages=messages,
                    tools=tools,
                    tool_choice="auto",
                    parallel_tool_calls=True,
                    # conversation_id=f"{context.get('channel_id')}:{context.get('author_id')}",
                    # response_format={"type": "text"},
                )
            except Exception as e:
                self.logger.error(f"OpenAI API call failed: {e}", exc_info=True)
                return "Sorry, I encountered an error while thinking.", 0.0, [], False

            response_message = response.choices[0].message
            messages.append(response_message)

            if not response_message.tool_calls:
                final_text = response_message.content or "I don't have a response for that."
                break

            tool_results_for_api = []
            for tool_call in response_message.tool_calls:
                fn_name = tool_call.function.name
                try:
                    fn_args = json.loads(tool_call.function.arguments)
                except json.JSONDecodeError:
                    fn_args = {}
                    self.logger.warning(f"Could not decode JSON args for {fn_name}: {tool_call.function.arguments}")

                if fn_name == "think_harder":
                    wants_escalation = True

                # Execute the function and store result for logging
                result = await self.function_caller.execute_function(fn_name, fn_args, _context=context)
                executed_tools.append({"function": fn_name, "result": result})

                # Prepare result to be sent back to the model
                tool_results_for_api.append({
                    "tool_call_id": tool_call.id,
                    "role": "tool",
                    "name": fn_name,
                    "content": json.dumps(result, default=str),
                })

            messages.extend(tool_results_for_api)
        else:
            final_text = "I seem to be stuck in a tool-use loop. Please try rephrasing your request."

        total_ms = (time.time() - loop_start_time) * 1000.0
        return final_text, total_ms, executed_tools, wants_escalation

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Main entry point for handling bot mentions."""
        if message.author.bot or not self.client or (self.bot.user not in message.mentions):
            return

        if config.AI_BANNED_ROLE_ID and message.guild:
            user_roles = [role.id for role in message.author.roles]
            if config.AI_BANNED_ROLE_ID in user_roles:
                await message.add_reaction("💤")
                return

        question = ai_conversation.clean_message_content(message.content, self.bot.user.id)
        if not question:
            return

        async with message.channel.typing():
            start_time = time.time()
            history = await self._get_recent_messages(message.channel, limit=config.CHANNEL_HISTORY_LIMIT, before=message)

            exec_context = {
                "guild_id": message.guild.id if message.guild else None,
                "channel_id": message.channel.id,
                "author_id": message.author.id,
                "message_id": message.id,
                "last_user_text": question,
            }

            interaction_id = start_ai_interaction(
                guild_id=exec_context["guild_id"], channel_id=exec_context["channel_id"],
                author_id=exec_context["author_id"], message_id=exec_context["message_id"],
                question=question,
                chat_history_json=json.dumps(
                    [{"id": m.id, "author": m.author.name, "content": m.content} for m in history], default=str)
            )

            # --- Lite Model Pass ---
            lite_messages = ai_conversation.build_conversation_messages(
                history, message.author, question,
                pro=False, message_id=message.id, bot_user_id=self.bot.user.id,
                prompt_loader=prompt_loader
            )
            lite_allowed_tools = config.AI_LITE_ALLOWED_TOOLS

            final_text, ms1, executed1, wants_escalation = await self._run_conversation_loop(
                messages=lite_messages, pro=False, allowed_functions=lite_allowed_tools, context=exec_context
            )

            final_executed = executed1
            pro_used = False
            total_model_ms = ms1

            # --- Pro Model Escalation ---
            if wants_escalation:
                pro_used = True
                self.logger.info(f"Escalating to pro model for interaction {interaction_id}.")
                pro_messages = ai_conversation.build_conversation_messages(
                    history, message.author, question,
                    pro=True, message_id=message.id, bot_user_id=self.bot.user.id,
                    prompt_loader=prompt_loader
                )

                final_text, ms2, executed2, _ = await self._run_conversation_loop(
                    messages=pro_messages, pro=True, allowed_functions=None, context=exec_context
                )
                final_executed.extend(executed2)
                total_model_ms += ms2

            try:
                await message.reply(final_text, mention_author=False)
            except Exception as e:
                self.logger.error(f"Failed to send Discord reply: {e}", exc_info=True)

            await self._maybe_handle_uploads(message, final_executed)

            complete_ai_interaction(
                interaction_id, pro_mode=pro_used,
                model_name=(config.AI_OPENAI_PRO_MODEL if pro_used else config.AI_OPENAI_MODEL),
                response_text=final_text, total_elapsed_ms=(time.time() - start_time) * 1000.0,
                gemini_total_ms=total_model_ms, discord_reply_ms=0.0,
                tool_calls_count=len(final_executed),
            )

    # --- Admin and Utility Functions ---

    async def _maybe_handle_uploads(self, message: discord.Message, function_results: List[Dict[str, Any]]):
        seen_uploads = set()
        for fr in function_results:
            res = fr.get("result")
            if isinstance(res, dict) and res.get("upload_file") and res.get("success"):
                filename = res.get("filename", "file.txt")
                content = res.get("content", "")
                if (filename, content) in seen_uploads: continue
                seen_uploads.add((filename, content))

                buf = io.BytesIO(content.encode("utf-8"))
                file = discord.File(fp=buf, filename=filename)
                await message.reply(content=res.get("message", "Here is the requested file."), file=file,
                                    mention_author=False)

    def _parse_message_id_or_link(self, value: Optional[str]) -> Optional[int]:
        if not value: return None
        v = value.strip().split('/')[-1]
        try:
            return int(v)
        except (ValueError, TypeError):
            return None

    def _build_inspection_report(self, interaction_row: dict, gemini_calls: List[dict], function_calls: List[dict],
                                 discord_steps: List[dict]) -> str:
        # This function is unchanged as it only reads from the database.
        # It's kept here for completeness.
        lines: List[str] = []
        iid = interaction_row.get('id')
        lines.append(f"AI Interaction #{iid}")
        lines.append(
            f"  Context: guild={interaction_row.get('guild_id')}, channel={interaction_row.get('channel_id')}, author={interaction_row.get('author_id')}")
        lines.append(f"  Question: {interaction_row.get('question')}")
        lines.append(f"  Response: {interaction_row.get('response_text')}")
        lines.append(
            f"  Totals: pro={bool(interaction_row.get('pro_mode'))}, model='{interaction_row.get('model_name')}', tool_calls={interaction_row.get('tool_calls_count')}")
        lines.append(
            f"  Timings (ms): total={interaction_row.get('total_elapsed_ms')}, model={interaction_row.get('gemini_total_ms')}")

        lines.append(f"\nGemini/OpenAI Calls ({len(gemini_calls)}):")
        if gemini_calls:
            for i, g in enumerate(gemini_calls, 1):
                lines.append(f"  [{i}] {g.get('elapsed_ms')}ms | {g.get('model_name')} | tools={g.get('tool_mode')}")
        else:
            lines.append("  (none)")

        lines.append(f"\nFunction Calls ({len(function_calls)}):")
        if function_calls:
            for fc in function_calls:
                lines.append(f"  - [{fc.get('sequence_index')}] {fc.get('function_name')} ({fc.get('elapsed_ms')}ms)")
                lines.append(f"    Params: {fc.get('params_json')}")
                lines.append(f"    Result: {fc.get('result_json')}")
        else:
            lines.append("  (none)")

        return "\n".join(lines)

    async def _send_long_ephemeral(self, interaction: discord.Interaction, text: str):
        # This function is unchanged.
        chunks = [text[i:i + config.DISCORD_MESSAGE_CHUNK_SIZE] for i in range(0, len(text), config.DISCORD_MESSAGE_CHUNK_SIZE)]
        first = True
        for chunk in chunks:
            msg = f"```\n{chunk}\n```"
            if first:
                if not interaction.response.is_done():
                    await interaction.response.send_message(msg, ephemeral=True)
                else:
                    await interaction.followup.send(msg, ephemeral=True)
                first = False
            else:
                await interaction.followup.send(msg, ephemeral=True)

    @app_commands.command(name="inspect_ai", description="Admin-only: inspect AI interaction by message ID or latest")
    @slash_admin_only()
    async def inspect_ai(self, interaction: discord.Interaction, message_id: Optional[str] = None):
        # This command logic is unchanged.
        await interaction.response.defer(ephemeral=True, thinking=True)
        channel = interaction.channel
        if not isinstance(channel, discord.TextChannel):
            await interaction.followup.send("Run this in a text channel.", ephemeral=True)
            return

        target_msg_id = self._parse_message_id_or_link(message_id)
        if target_msg_id:
            try:
                msg = await channel.fetch_message(target_msg_id)
                if msg.reference and msg.reference.message_id:
                    target_msg_id = msg.reference.message_id
            except (discord.NotFound, discord.HTTPException):
                pass

        if not target_msg_id:
            async for m in channel.history(limit=config.INSPECT_HISTORY_LIMIT):
                if m.author.id == self.bot.user.id and m.reference and m.reference.message_id:
                    target_msg_id = m.reference.message_id
                    break

        if not target_msg_id:
            await interaction.followup.send("Could not find a recent AI interaction to inspect.", ephemeral=True)
            return

        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM ai_interactions WHERE message_id = ? ORDER BY id DESC LIMIT 1", (target_msg_id,))
            row = cur.fetchone()

        if not row:
            await interaction.followup.send(f"No AI interaction found for message ID {target_msg_id}", ephemeral=True)
            return

        interaction_row = dict(row)
        interaction_id = interaction_row.get("id")

        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM ai_gemini_calls WHERE interaction_id = ? ORDER BY id ASC", (interaction_id,))
            gemini_calls = [dict(r) for r in cur.fetchall()]
            cur.execute("SELECT * FROM ai_function_calls WHERE interaction_id = ? ORDER BY sequence_index ASC, id ASC",
                        (interaction_id,))
            function_calls = [dict(r) for r in cur.fetchall()]
            cur.execute("SELECT * FROM ai_discord_steps WHERE interaction_id = ? ORDER BY id ASC", (interaction_id,))
            discord_steps = [dict(r) for r in cur.fetchall()]

        report = self._build_inspection_report(interaction_row, gemini_calls, function_calls, discord_steps)
        await self._send_long_ephemeral(interaction, report)


async def setup(bot: commands.Bot):
    """Standard cog setup function."""
    await bot.add_cog(AIMentionCog(bot))
