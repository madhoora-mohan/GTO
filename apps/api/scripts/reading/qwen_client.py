"""
Single entry point for every local Qwen3.5:9b call in the reading
comprehension pipeline (Track A's distractor/question generation AND
Track B's passage/question generation both import call_qwen() from here —
do not write a second copy of this logic anywhere else).

Why this needs to exist at all (the "thinking too much and crashing" problem):
Qwen3.5 is a "thinking" model — by default it writes out a long internal
reasoning trace before its real answer. For short, format-constrained tasks
like "output this exact JSON shape," that reasoning trace is pure overhead:
it's slow, it sometimes runs away in length, and it has nothing to do with
the actual quality of the JSON we want back.

The fix is `think: false`, but it MUST be sent as a top-level field in the
Ollama API request body — not typed into the prompt text as "/no_think",
and not nested inside the "options" dict. Both of those alternate spots are
silently ignored by current Ollama versions for this model (confirmed via
manual curl test, see Step 3.4 of the handoff doc, and multiple open Ollama
GitHub issues #14809/#14617/#14502). We verified manually before writing
this file that passing think=False as a kwarg to ollama.Client().chat()
actually produces clean, thinking-free output.
"""

import json
import time

from ollama import Client

_client = Client()
MODEL = "qwen3.5:9b"
MAX_RETRIES = 2
TIMEOUT_SECONDS = 90

# Logged every CALL_LOG_INTERVAL calls so VRAM trends can be eyeballed
# against data/raw/reading/vram_log.csv during a long unattended batch.
_call_count = 0
CALL_LOG_INTERVAL = 50


class QwenGenerationError(Exception):
    """Raised when call_qwen() exhausts all retries. Callers MUST catch this
    and log + skip the current item — never let one bad generation crash an
    entire overnight batch run."""


def call_qwen(prompt: str, expect_json: bool = True, num_ctx: int = 4096) -> dict | str:
    """
    Call Qwen3.5:9b with thinking disabled.

    If expect_json is True (the normal case for this pipeline), the
    response text is parsed as JSON. If parsing fails, we don't just retry
    with the identical prompt — past experience shows a model that produced
    bad JSON once tends to produce the exact same bad JSON again from the
    same input. Instead we append a short, explicit correction message
    ("your last output wasn't valid JSON, try again") so the retry has an
    actually different chance of succeeding.

    num_ctx defaults to 4096 (safe for every prompt in this pipeline).
    Track B's passage/question prompts are reliably small (~1100 chars), so
    generate_track_b.py passes num_ctx=2048 explicitly to save VRAM. Track
    A's distractor/question prompts can carry up to a 1000-char Wikipedia
    context and run close to 2048 tokens worst-case combined with the
    response — those callers keep the 4096 default rather than risk a
    silent context-window truncation.

    Raises QwenGenerationError after MAX_RETRIES+1 failed attempts.
    """
    global _call_count
    _call_count += 1
    if _call_count % CALL_LOG_INTERVAL == 0:
        print(f"  [qwen_client] Calls so far: {_call_count} — check vram_log.csv")

    last_error: Exception | None = None

    for attempt in range(MAX_RETRIES + 1):
        try:
            response = _client.chat(
                model=MODEL,
                messages=[{"role": "user", "content": prompt}],
                think=False,
                options={
                    "temperature": 0.7,
                    "num_ctx": num_ctx,
                },
            )
            content = response["message"]["content"].strip()

            if not expect_json:
                return content

            # The prompts explicitly say "no markdown code fences," but
            # models don't always listen — strip ```json ... ``` wrappers
            # defensively. This is a fallback, not something to rely on
            # instead of the prompt instruction.
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
                content = content.strip()

            return json.loads(content)

        except json.JSONDecodeError as e:
            last_error = e
            if attempt < MAX_RETRIES:
                prompt = (
                    f"{prompt}\n\n前回の出力はJSON形式として無効でした。"
                    f"必ず有効なJSONオブジェクトのみを出力してください。"
                    f"説明文やマークダウンのコードブロックは一切含めないでください。"
                )
                time.sleep(1)
                continue

        except Exception as e:
            last_error = e
            if attempt < MAX_RETRIES:
                time.sleep(2)
                continue

    raise QwenGenerationError(
        f"Failed after {MAX_RETRIES + 1} attempts: {last_error}"
    )
