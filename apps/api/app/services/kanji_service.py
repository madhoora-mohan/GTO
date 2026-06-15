import uuid
from typing import Literal

from sqlalchemy import func, nulls_last, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import PageParams
from app.models.component import Component
from app.models.kanji import Kanji
from app.models.kanji_component import KanjiComponent
from app.models.kanji_sentence import KanjiSentence
from app.models.sentence import Sentence
from app.models.user_mnemonic import UserMnemonic
from app.services.jlpt import JLPT_RANK, jlpt_order

# Ordering for example sentences on detail views: N5 first, NULL last,
# then sentence ID as a stable tie-breaker.
_JLPT_ORDER = jlpt_order(Sentence.jlpt)

# Used by GET /kanji's jlpt_max filter — "this level or easier".
_KANJI_JLPT_ORDER = jlpt_order(Kanji.jlpt)

# Difficulty rank used by sentence_jlpt_max — lower is easier. NULL (rank 6,
# via _JLPT_ORDER) is always excluded since it's never <= 5.
_JLPT_RANK = JLPT_RANK


async def list_kanji(
    db: AsyncSession,
    page_params: PageParams,
    jlpt: Literal["N1", "N2", "N3", "N4", "N5"] | None = None,
    jlpt_max: Literal["N1", "N2", "N3", "N4", "N5"] | None = None,
    grade: int | None = None,
    stroke_count: int | None = None,
) -> tuple[list[Kanji], int]:
    """Return (rows, total) for GET /kanji, applying optional jlpt, jlpt_max,
    grade, stroke_count filters. jlpt and jlpt_max are mutually exclusive
    (caller must validate)."""
    stmt = select(Kanji)
    count_stmt = select(func.count()).select_from(Kanji)

    if jlpt is not None:
        stmt = stmt.where(Kanji.jlpt == jlpt)
        count_stmt = count_stmt.where(Kanji.jlpt == jlpt)
    elif jlpt_max is not None:
        stmt = stmt.where(_KANJI_JLPT_ORDER <= JLPT_RANK[jlpt_max])
        count_stmt = count_stmt.where(_KANJI_JLPT_ORDER <= JLPT_RANK[jlpt_max])
    if grade is not None:
        count_stmt = count_stmt.where(Kanji.grade == grade)
        stmt = stmt.where(Kanji.grade == grade)
    if stroke_count is not None:
        stmt = stmt.where(Kanji.stroke_count == stroke_count)
        count_stmt = count_stmt.where(Kanji.stroke_count == stroke_count)

    total = (await db.execute(count_stmt)).scalar_one()

    stmt = (
        stmt.order_by(nulls_last(Kanji.frequency.asc()))
        .offset(page_params.offset)
        .limit(page_params.page_size)
    )
    rows = (await db.execute(stmt)).scalars().all()

    return list(rows), total


async def get_kanji(db: AsyncSession, character: str) -> Kanji | None:
    """Return the Kanji row for 'character', or None if it does not exist"""
    return await db.get(Kanji, character)


async def get_components(db: AsyncSession, character: str) -> list[Component]:
    """Visual components this kanji is made of."""
    stmt = (
        select(Component)
        .join(KanjiComponent, KanjiComponent.component_id == Component.id)
        .where(KanjiComponent.kanji_char == character)
    )
    rows = (await db.execute(stmt)).scalars().all()
    return list(rows)


async def get_sentences(
    db: AsyncSession,
    character: str,
    sentence_jlpt: Literal["N1", "N2", "N3", "N4", "N5"] | None = None,
    sentence_jlpt_max: Literal["N1", "N2", "N3", "N4", "N5"] | None = None,
) -> list[Sentence]:
    """Up to 10 example sentences for this kanji, JLPT-ordered (N5 first,
    NULL last) then sentence ID as a stable tie-breaker.

    - `sentence_jlpt`: only sentences at exactly that level.
    - `sentence_jlpt_max`: sentences at that level or easier (NULL excluded).
    Mutually exclusive — caller must not pass both.
    """
    stmt = (
        select(Sentence)
        .join(KanjiSentence, KanjiSentence.sentence_id == Sentence.id)
        .where(KanjiSentence.kanji_char == character)
    )
    if sentence_jlpt is not None:
        stmt = stmt.where(Sentence.jlpt == sentence_jlpt)
    elif sentence_jlpt_max is not None:
        stmt = stmt.where(_JLPT_ORDER <= _JLPT_RANK[sentence_jlpt_max])

    stmt = stmt.order_by(_JLPT_ORDER, Sentence.id.asc()).limit(10)
    rows = (await db.execute(stmt)).scalars().all()
    return list(rows)


async def get_user_mnemonic(db: AsyncSession, user_id: uuid.UUID, character: str) -> str | None:
    """The authenticated user's personal mnemonic override, or None if unset."""
    stmt = select(UserMnemonic.mnemonic).where(
        UserMnemonic.user_id == user_id,
        UserMnemonic.kanji_character == character,
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def set_user_mnemonic(
    db: AsyncSession, user_id: uuid.UUID, character: str, mnemonic: str
) -> str | None:
    """Set or clear the user's mnemonic override for this kanji.

    Empty string deletes the override (revert to LLM default) and returns
    None. Non-empty upserts the override and returns the new value.
    """
    stmt = select(UserMnemonic).where(
        UserMnemonic.user_id == user_id,
        UserMnemonic.kanji_character == character,
    )
    existing = (await db.execute(stmt)).scalar_one_or_none()

    if mnemonic == "":
        if existing is not None:
            await db.delete(existing)
            await db.commit()
        return None

    if existing is not None:
        existing.mnemonic = mnemonic
    else:
        db.add(UserMnemonic(user_id=user_id, kanji_character=character, mnemonic=mnemonic))
    await db.commit()
    return mnemonic
