import argparse
import json
import os
import sys
from datetime import datetime
from typing import Any, Optional

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, '..'))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from utils.db import get_db_connection, DB_FILE  # noqa: E402


def _truncate(value: str, max_len: int = 500) -> str:
    if value is None:
        return ''
    text = str(value)
    return text if len(text) <= max_len else text[: max_len - 3] + '...'


def _json_pretty(value: Any, max_len: int = 800) -> str:
    try:
        text = json.dumps(value, ensure_ascii=False, indent=2, default=str)
    except Exception:
        try:
            text = json.dumps(value, ensure_ascii=False, default=str)
        except Exception:
            text = str(value)
    return _truncate(text, max_len=max_len)


def _ensure_db_path():
    """Make sure database connections use the repo's sqlite file regardless of CWD."""
    db_path = os.path.join(REPO_ROOT, 'verified_users.db')
    try:
        DB_FILE = db_path
    except Exception:
        pass


def _find_interaction_id_by_message_id(message_id: int) -> Optional[int]:
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
                SELECT id FROM ai_interactions
                WHERE message_id = ?
                ORDER BY id DESC
                LIMIT 1
            """,
            (message_id,),
        )
        row = cur.fetchone()
        return int(row['id']) if row else None


def _load_interaction(interaction_id: int) -> Optional[dict]:
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM ai_interactions WHERE id = ?", (interaction_id,))
        row = cur.fetchone()
        return dict(row) if row else None


def _load_gemini_calls(interaction_id: int) -> list:
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM ai_gemini_calls WHERE interaction_id = ? ORDER BY id ASC",
            (interaction_id,),
        )
        return [dict(r) for r in cur.fetchall()]


def _load_function_calls(interaction_id: int) -> list:
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM ai_function_calls WHERE interaction_id = ? ORDER BY sequence_index ASC, id ASC",
            (interaction_id,),
        )
        return [dict(r) for r in cur.fetchall()]


def _load_discord_steps(interaction_id: int) -> list:
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM ai_discord_steps WHERE interaction_id = ? ORDER BY id ASC",
            (interaction_id,),
        )
        return [dict(r) for r in cur.fetchall()]


def print_interaction_report(*, message_id: Optional[int] = None, interaction_id: Optional[int] = None) -> int:
    _ensure_db_path()

    if not interaction_id and not message_id:
        print("Error: provide either --message-id or --interaction-id")
        return 2

    if not interaction_id and message_id:
        interaction_id = _find_interaction_id_by_message_id(message_id)
        if not interaction_id:
            print(f"No ai_interaction found for message_id={message_id}")
            return 1

    interaction = _load_interaction(interaction_id)
    if not interaction:
        print(f"Interaction not found: id={interaction_id}")
        return 1

    gemini_calls = _load_gemini_calls(interaction_id)
    function_calls = _load_function_calls(interaction_id)
    discord_steps = _load_discord_steps(interaction_id)

    print("=" * 80)
    print(f"AI Interaction #{interaction_id}")
    print("=" * 80)

    print("- Context:")
    print(f"  created_at    : {interaction.get('created_at')}")
    print(f"  guild_id      : {interaction.get('guild_id')}")
    print(f"  channel_id    : {interaction.get('channel_id')}")
    print(f"  author_id     : {interaction.get('author_id')}")
    print(f"  message_id    : {interaction.get('message_id')}")
    print()

    question = interaction.get('question') or ''
    response_text = interaction.get('response_text') or ''
    print("- Conversation:")
    print(f"  Question      : {_truncate(question, 800)}")
    print(f"  Response (tr) : {_truncate(response_text, 800)}")
    print()

    chat_json = interaction.get('chat_history_json')
    print("- Chat history:")
    try:
        history = json.loads(chat_json) if chat_json else []
    except Exception:
        history = []
    if history:
        for idx, item in enumerate(history, start=1):
            author = item.get('author') or item.get('author_id')
            is_bot = 'bot' if item.get('is_bot') else 'user'
            content = _truncate(item.get('content', ''), 200)
            print(f"  [{idx:02d}] {is_bot:>4} | {author}: {content}")
    else:
        print("  (no history)")
    print()

    print("- Totals:")
    print(f"  pro_mode      : {bool(interaction.get('pro_mode'))}")
    print(f"  model_name    : {interaction.get('model_name')}")
    print(f"  tool_calls    : {interaction.get('tool_calls_count')}")
    print(f"  gemini_total  : {interaction.get('gemini_total_ms')} ms")
    print(f"  discord_reply : {interaction.get('discord_reply_ms')} ms")
    print(f"  total_elapsed : {interaction.get('total_elapsed_ms')} ms")
    print()

    print(f"- Gemini calls ({len(gemini_calls)}):")
    if gemini_calls:
        for i, call in enumerate(gemini_calls, start=1):
            allow_funcs = []
            try:
                allow_funcs = json.loads(call.get('allow_functions_json') or '[]')
            except Exception:
                pass
            print(f"  [{i:02d}] {call.get('elapsed_ms')} ms | {call.get('model_name')} | tool_mode={call.get('tool_mode')} | allow={allow_funcs}")
    else:
        print("  (none)")
    print()

    print(f"- Function calls ({len(function_calls)}):")
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
            print(f"  - [{seq}] {name} | {ms} ms")
            if params_obj is not None:
                print(f"      params : {_json_pretty(params_obj, 600)}")
            if result_obj is not None:
                print(f"      result : {_json_pretty(result_obj, 600)}")
    else:
        print("  (none)")
    print()

    print(f"- Discord steps ({len(discord_steps)}):")
    if discord_steps:
        for ds in discord_steps:
            name = ds.get('step_name')
            ms = ds.get('elapsed_ms')
            extra = ds.get('extra_json')
            try:
                extra_obj = json.loads(extra) if extra else None
            except Exception:
                extra_obj = extra
            print(f"  - {name} | {ms} ms")
            if extra_obj is not None:
                print(f"      extra  : {_json_pretty(extra_obj, 400)}")
    else:
        print("  (none)")
    print()

    print("(end)")
    return 0


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(description="Inspect AI interaction by message ID or interaction ID.")
    parser.add_argument('--message-id', type=int, help='Discord message ID associated with the interaction')
    parser.add_argument('--interaction-id', type=int, help='Internal ai_interactions.id to inspect')
    args = parser.parse_args(argv)
    return print_interaction_report(message_id=args.message_id, interaction_id=args.interaction_id)


if __name__ == '__main__':
    sys.exit(main())


