"""
Backfill kanji_vocab.reading_type based on kana matching.

Primary strategy — furigana lookup (most accurate):
  For each (kanji_char, vocab_id) row, find the furigana segment whose ruby
  exactly equals the kanji character and use its rt (reading) directly.
  Compare that rt against the kanji's onyomi/kunyomi lists.

Fallback strategy — vocab reading prefix match:
  If furigana is absent or no single-char segment matches, fall back to
  checking whether the full vocab reading starts with any on/kun reading.
  This handles single-kanji words and simple compounds.

Normalisation applied to both strategies:
  - Onyomi (katakana) is converted to hiragana for comparison.
  - Kunyomi dot separators are stripped ("た.べる" -> "た").
  - Kunyomi leading hyphens are stripped ("-こ" -> "こ").

Result:
  "on"  — reading matched an onyomi entry
  "kun" — reading matched a kunyomi entry
  null  — could not be resolved (irregular or rendaku reading)

IDEMPOTENT — safe to re-run; always overwrites all rows.
"""

import asyncio

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.models.kanji import Kanji
from app.models.kanji_vocab import KanjiVocab
from app.models.vocab import Vocab


def kata_to_hira(s: str) -> str:
    return "".join(chr(ord(c) - 0x60) if "ァ" <= c <= "ン" else c for c in s)


def normalise_onyomi(readings: list[str]) -> list[str]:
    return [kata_to_hira(r) for r in readings]


def normalise_kunyomi(readings: list[str]) -> list[str]:
    result = []
    for r in readings:
        r = r.lstrip("-")   # strip leading hyphen (suffix markers like "-こ")
        r = r.split(".")[0]  # strip okurigana after dot
        if r:
            result.append(r)
    return result


def resolve_via_furigana(kanji_char: str, furigana: list[dict], on_hira: list[str], kun_stems: list[str]) -> str | None:
    """Find the segment for this kanji and match its rt against on/kun lists."""
    for seg in furigana:
        if seg.get("ruby") == kanji_char:
            rt = seg.get("rt")
            if not rt:
                continue
            for on in on_hira:
                if rt == on or rt.startswith(on):
                    return "on"
            for kun in kun_stems:
                if rt == kun or rt.startswith(kun):
                    return "kun"
            # Segment found but reading didn't match — stop, don't fall through
            return None
    return None  # no matching segment


def resolve_via_prefix(vocab_reading: str, on_hira: list[str], kun_stems: list[str]) -> str | None:
    """Check if the full vocab reading starts with any on/kun reading."""
    for on in on_hira:
        if vocab_reading.startswith(on):
            return "on"
    for kun in kun_stems:
        if vocab_reading.startswith(kun):
            return "kun"
    return None


async def backfill():
    engine = create_async_engine(
        settings.async_database_url,
        connect_args={"ssl": "require"},
        echo=False,
    )
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        rows = (await session.execute(select(KanjiVocab))).scalars().all()
        print(f"Total kanji_vocab rows: {len(rows)}")

        kanji_map = {k.character: k for k in (await session.execute(select(Kanji))).scalars().all()}
        vocab_map = {v.id: v for v in (await session.execute(select(Vocab))).scalars().all()}

        resolved_on = 0
        resolved_kun = 0
        unresolved = 0
        updates = []

        for row in rows:
            kanji = kanji_map.get(row.kanji_char)
            vocab = vocab_map.get(row.vocab_id)
            if not kanji or not vocab:
                continue

            on_hira = normalise_onyomi(kanji.onyomi or [])
            kun_stems = normalise_kunyomi(kanji.kunyomi or [])
            reading_type = None

            # Strategy 1: furigana lookup
            if vocab.furigana:
                reading_type = resolve_via_furigana(row.kanji_char, vocab.furigana, on_hira, kun_stems)

            # Strategy 2: prefix match on full vocab reading (fallback)
            if reading_type is None:
                reading_type = resolve_via_prefix(vocab.reading, on_hira, kun_stems)

            if reading_type == "on":
                resolved_on += 1
            elif reading_type == "kun":
                resolved_kun += 1
            else:
                unresolved += 1

            updates.append({
                "b_kanji_char": row.kanji_char,
                "b_vocab_id": row.vocab_id,
                "b_reading_type": reading_type,
            })

        print(f"Computed {len(updates)} updates (on={resolved_on}, kun={resolved_kun}, unresolved={unresolved})")
        print("Sending batched update...")

        if updates:
            await session.execute(
                text(
                    "UPDATE kanji_vocab SET reading_type = :b_reading_type "
                    "WHERE kanji_char = :b_kanji_char AND vocab_id = :b_vocab_id"
                ),
                updates,
            )

        print("Committing...")
        await session.commit()
        print("Committed.")
        print(f"Done. on={resolved_on}, kun={resolved_kun}, unresolved={unresolved}")


if __name__ == "__main__":
    asyncio.run(backfill())
