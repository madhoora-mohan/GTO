import uuid
from typing import Literal

from sqlalchemy import case, func, nulls_last, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import PageParams
from app.models.component import Component
from app.models.kanji import Kanji
from app.models.kanji_component import KanjiComponent
from app.models.kanji_sentence import KanjiSentence
from app.models.kanji_vocab import KanjiVocab
from app.models.sentence import Sentence
from app.models.user_mnemonic import UserMnemonic
from app.models.vocab import Vocab
from app.services.jlpt import JLPT_RANK, jlpt_order
from app.services.practice_service import level_counts, resolve_levels

# Used by GET /kanji's jlpt_max filter — "this level or easier".
_KANJI_JLPT_ORDER = jlpt_order(Kanji.jlpt)


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


async def get_sentences(db: AsyncSession, character: str) -> list[Sentence]:
    """Up to 10 example sentences for this kanji, ordered by sentence ID."""
    stmt = (
        select(Sentence)
        .join(KanjiSentence, KanjiSentence.sentence_id == Sentence.id)
        .where(KanjiSentence.kanji_char == character)
        .order_by(Sentence.id.asc())
        .limit(10)
    )
    rows = (await db.execute(stmt)).scalars().all()
    return list(rows)


async def get_vocab_words(db: AsyncSession, character: str) -> list[tuple[Vocab, str | None]]:
    """Up to 20 vocab words containing this kanji, with their reading_type,
    ordered N5 first (NULL last), common words first, then by vocab id."""
    stmt = (
        select(Vocab, KanjiVocab.reading_type)
        .join(KanjiVocab, KanjiVocab.vocab_id == Vocab.id)
        .where(KanjiVocab.kanji_char == character)
        .order_by(
            case(
                {level: rank for level, rank in JLPT_RANK.items()},
                value=Vocab.jlpt,
                else_=99,
            ).asc(),
            case((Vocab.is_common == True, 0), else_=1).asc(),  # noqa: E712
            Vocab.id.asc(),
        )
        .limit(20)
    )
    rows = (await db.execute(stmt)).all()
    return [(v, reading_type) for v, reading_type in rows]


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


async def list_user_mnemonics(
    db: AsyncSession, user_id: uuid.UUID, page_params: PageParams
) -> tuple[list[UserMnemonic], int]:
    """Return (rows, total) of this user's custom kanji mnemonics, ordered by
    updated_at descending (most recently edited first). Every row in
    user_mnemonics already has a non-null mnemonic — set_user_mnemonic
    deletes the row instead of writing an empty one."""
    stmt = select(UserMnemonic).where(UserMnemonic.user_id == user_id)
    count_stmt = select(func.count()).select_from(UserMnemonic).where(UserMnemonic.user_id == user_id)

    total = (await db.execute(count_stmt)).scalar_one()

    stmt = (
        stmt.order_by(UserMnemonic.updated_at.desc())
        .offset(page_params.offset)
        .limit(page_params.page_size)
    )
    rows = (await db.execute(stmt)).scalars().all()

    return list(rows), total


async def get_practice_batch(
    db: AsyncSession,
    jlpt_level: Literal["N1", "N2", "N3", "N4", "N5"],
    scope: Literal["exact", "and_below"],
    distribution: Literal["balanced", "challenge"],
    count: int,
    exclude: set[str],
) -> list[Kanji]:
    """A random, no-duplicate batch of kanji for a Practice session, split
    across the resolved level range per `distribution`. If a level doesn't
    have enough rows (after excluding `exclude`) to fill its share, that
    level's batch is simply smaller — counts are not redistributed."""
    levels = resolve_levels(jlpt_level, scope)
    counts = level_counts(levels, distribution, count)

    rows: list[Kanji] = []
    for level, n in counts.items():
        if n <= 0:
            continue
        stmt = select(Kanji).where(Kanji.jlpt == level)
        if exclude:
            stmt = stmt.where(Kanji.character.notin_(exclude))
        stmt = stmt.order_by(func.random()).limit(n)
        rows.extend((await db.execute(stmt)).scalars().all())

    return rows


async def get_distractor_meanings(db: AsyncSession, kanji: Kanji, count: int = 3) -> list[str]:
    """Up to `count` distinct meaning strings drawn from other kanji at the
    same jlpt level as `kanji` (or other jlpt-less kanji, if `kanji.jlpt` is
    None), excluding `kanji`'s own meanings. May return fewer than `count`
    if the same-level pool is too small."""
    stmt = select(Kanji.meanings).where(Kanji.character != kanji.character)
    stmt = (
        stmt.where(Kanji.jlpt.is_(None)) if kanji.jlpt is None else stmt.where(Kanji.jlpt == kanji.jlpt)
    )
    # Oversample candidates — most rows will contribute a usable meaning,
    # but some may overlap with kanji's own meanings or each other.
    stmt = stmt.order_by(func.random()).limit(count * 10)
    rows = (await db.execute(stmt)).scalars().all()

    own_meanings = set(kanji.meanings)
    distractors: list[str] = []
    for meanings in rows:
        for meaning in meanings:
            if meaning in own_meanings or meaning in distractors:
                continue
            distractors.append(meaning)
            if len(distractors) == count:
                return distractors

    return distractors
