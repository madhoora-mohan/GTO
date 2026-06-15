from typing import Literal

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import PageParams
from app.models.sentence import Sentence
from app.models.vocab import Vocab
from app.models.vocab_sentence import VocabSentence
from app.services.jlpt import JLPT_RANK, jlpt_order

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


async def get_sentences(db: AsyncSession, vocab_id: str) -> list[Sentence]:
    """Up to 10 example sentences for this vocab, ordered by sentence ID."""
    stmt = (
        select(Sentence)
        .join(VocabSentence, VocabSentence.sentence_id == Sentence.id)
        .where(VocabSentence.vocab_id == vocab_id)
        .order_by(Sentence.id.asc())
        .limit(10)
    )
    rows = (await db.execute(stmt)).scalars().all()
    return list(rows)
