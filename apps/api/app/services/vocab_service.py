from typing import Literal

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import PageParams
from app.models.sentence import Sentence
from app.models.vocab import Vocab
from app.services.jlpt import JLPT_RANK, jlpt_order
from app.services.practice_service import level_counts, resolve_levels

_VOCAB_JLPT_ORDER = jlpt_order(Vocab.jlpt)


async def list_vocab(
    db: AsyncSession,
    page_params: PageParams,
    jlpt: Literal["N1", "N2", "N3", "N4", "N5"] | None = None,
    jlpt_max: Literal["N1", "N2", "N3", "N4", "N5"] | None = None,
    is_common: bool | None = None,
    search: str | None = None,
) -> tuple[list[Vocab], int]:
    """Return (rows, total) for GET /vocab, applying optional jlpt, jlpt_max,
    is_common, search filters. jlpt and jlpt_max are mutually exclusive
    (caller must validate)."""
    stmt = select(Vocab)
    count_stmt = select(func.count()).select_from(Vocab)

    if jlpt is not None:
        stmt = stmt.where(Vocab.jlpt == jlpt)
        count_stmt = count_stmt.where(Vocab.jlpt == jlpt)
    elif jlpt_max is not None:
        stmt = stmt.where(_VOCAB_JLPT_ORDER <= JLPT_RANK[jlpt_max])
        count_stmt = count_stmt.where(_VOCAB_JLPT_ORDER <= JLPT_RANK[jlpt_max])
    if is_common is not None:
        stmt = stmt.where(Vocab.is_common == is_common)
        count_stmt = count_stmt.where(Vocab.is_common == is_common)
    if search is not None:
        term = f"%{search}%"
        condition = or_(Vocab.word.ilike(term), Vocab.reading.ilike(term))
        stmt = stmt.where(condition)
        count_stmt = count_stmt.where(condition)

    total = (await db.execute(count_stmt)).scalar_one()

    stmt = (
        stmt.order_by(_VOCAB_JLPT_ORDER, Vocab.word.asc())
        .offset(page_params.offset)
        .limit(page_params.page_size)
    )
    rows = (await db.execute(stmt)).scalars().all()

    return list(rows), total


async def get_vocab(db: AsyncSession, vocab_id: str) -> Vocab | None:
    """Return the Vocab row for 'vocab_id', or None if it does not exist"""
    return await db.get(Vocab, vocab_id)


async def get_sentences(db: AsyncSession, vocab_word: str) -> list[Sentence]:
    """Up to 10 example sentences containing this vocab word, using GIN trigram index."""
    stmt = (
        select(Sentence)
        .where(Sentence.japanese.contains(vocab_word))
        .order_by(Sentence.id.asc())
        .limit(10)
    )
    rows = (await db.execute(stmt)).scalars().all()
    return list(rows)


async def get_practice_batch(
    db: AsyncSession,
    jlpt_level: Literal["N1", "N2", "N3", "N4", "N5"],
    scope: Literal["exact", "and_below"],
    distribution: Literal["balanced", "challenge"],
    count: int,
    exclude: set[str],
) -> list[Vocab]:
    """A random, no-duplicate batch of vocab for a Practice session, split
    across the resolved level range per `distribution`. If a level doesn't
    have enough rows (after excluding `exclude`) to fill its share, that
    level's batch is simply smaller — counts are not redistributed."""
    levels = resolve_levels(jlpt_level, scope)
    counts = level_counts(levels, distribution, count)

    rows: list[Vocab] = []
    for level, n in counts.items():
        if n <= 0:
            continue
        stmt = select(Vocab).where(Vocab.jlpt == level)
        if exclude:
            stmt = stmt.where(Vocab.id.notin_(exclude))
        stmt = stmt.order_by(func.random()).limit(n)
        rows.extend((await db.execute(stmt)).scalars().all())

    return rows


async def get_distractor_meanings(db: AsyncSession, vocab: Vocab, count: int = 3) -> list[str]:
    """Up to `count` distinct definition strings drawn from other vocab at
    the same jlpt level as `vocab` (or other jlpt-less vocab, if `vocab.jlpt`
    is None), excluding `vocab`'s own definitions. May return fewer than
    `count` if the same-level pool is too small."""
    stmt = select(Vocab.meanings).where(Vocab.id != vocab.id)
    stmt = (
        stmt.where(Vocab.jlpt.is_(None)) if vocab.jlpt is None else stmt.where(Vocab.jlpt == vocab.jlpt)
    )
    stmt = stmt.order_by(func.random()).limit(count * 10)
    rows = (await db.execute(stmt)).scalars().all()

    own_definitions = {
        definition for meaning in vocab.meanings for definition in (meaning.get("definitions") or [])
    }
    distractors: list[str] = []
    for meanings in rows:
        for meaning in meanings:
            for definition in meaning.get("definitions") or []:
                if definition in own_definitions or definition in distractors:
                    continue
                distractors.append(definition)
                if len(distractors) == count:
                    return distractors

    return distractors


async def get_distractor_words(db: AsyncSession, vocab: Vocab, count: int = 3) -> list[str]:
    """Up to `count` distinct vocab `word` strings drawn from other vocab at
    the same jlpt level as `vocab` (or other jlpt-less vocab, if `vocab.jlpt`
    is None), excluding `vocab`'s own word. Used for sentence-cloze MCQ
    options, which are whole words, not meanings."""
    stmt = select(Vocab.word).where(Vocab.id != vocab.id, Vocab.word != vocab.word)
    stmt = (
        stmt.where(Vocab.jlpt.is_(None)) if vocab.jlpt is None else stmt.where(Vocab.jlpt == vocab.jlpt)
    )
    stmt = stmt.order_by(func.random()).limit(count * 5)
    rows = (await db.execute(stmt)).scalars().all()

    distractors: list[str] = []
    for word in rows:
        if word in distractors:
            continue
        distractors.append(word)
        if len(distractors) == count:
            break

    return distractors
