# WHAT: Builds the sentence-cloze batch for GET /practice/sentence-cloze —
#       a real example sentence with the target vocab word blanked out
#       (pre-marked with a "___" placeholder), plus 4 same-JLPT-level MCQ
#       options.
# WHY:  Both Practice entry points (Kanji, Vocab) end up needing the exact
#       same artifact — "a sentence, a word that appears in it verbatim,
#       and same-level distractor words" — so this always resolves down to
#       a vocab word + a sentence containing that word, regardless of which
#       entry point picked the word. For the kanji entry point, the target
#       word is one of that kanji's vocab_words (via kanji_vocab), not the
#       bare kanji character — blanking only the kanji character was
#       rejected during design (surrounding kana can give the answer away).
#       Reusing vocab_service.get_sentences (substring match on the word,
#       backed by the sentences.japanese GIN trigram index) for both entry
#       points guarantees the blanked word actually appears verbatim in the
#       sentence, rather than risking a sentence that contains the kanji in
#       a *different* word.

import random
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sentence import Sentence
from app.models.vocab import Vocab
from app.services import kanji_service, vocab_service

# How many extra candidates to pull beyond `count`, since some candidates
# won't have a usable sentence or enough distractors and get skipped.
_OVERSAMPLE_FACTOR = 3
_MAX_CANDIDATES = 50


def _build_cloze_item(sentence: Sentence, word: str, distractor_words: list[str]) -> dict:
    options = [word, *distractor_words[:3]]
    random.shuffle(options)
    return {
        # count=1: only the first occurrence is blanked, so the frontend
        # never has to search-and-replace (and risk hitting the wrong one
        # if the word appears more than once in the sentence).
        "sentence_japanese": sentence.japanese.replace(word, "___", 1),
        "sentence_english": sentence.english,
        "blanked_word": word,
        "options": options,
    }


async def _vocab_cloze_items(
    db: AsyncSession,
    jlpt_level: str,
    scope: Literal["exact", "and_below"],
    distribution: Literal["balanced", "challenge"],
    count: int,
    exclude: set[str],
) -> list[dict]:
    candidates = await vocab_service.get_practice_batch(
        db, jlpt_level, scope, distribution, min(count * _OVERSAMPLE_FACTOR, _MAX_CANDIDATES), exclude
    )

    items: list[dict] = []
    used_sentence_ids: set[int] = set()
    for vocab in candidates:
        if len(items) == count:
            break
        item = await _try_build_item(db, vocab, used_sentence_ids)
        if item is not None:
            items.append(item)
    return items


async def _kanji_cloze_items(
    db: AsyncSession,
    jlpt_level: str,
    scope: Literal["exact", "and_below"],
    distribution: Literal["balanced", "challenge"],
    count: int,
    exclude: set[str],
) -> list[dict]:
    candidate_kanji = await kanji_service.get_practice_batch(
        db, jlpt_level, scope, distribution, min(count * _OVERSAMPLE_FACTOR, _MAX_CANDIDATES), exclude
    )

    items: list[dict] = []
    used_sentence_ids: set[int] = set()
    used_words: set[str] = set()
    for kanji in candidate_kanji:
        if len(items) == count:
            break
        vocab_words = await kanji_service.get_vocab_words(db, kanji.character)
        random.shuffle(vocab_words)
        for vocab, _reading_type in vocab_words:
            if vocab.word in used_words:
                continue
            item = await _try_build_item(db, vocab, used_sentence_ids)
            if item is not None:
                used_words.add(vocab.word)
                items.append(item)
                break
    return items


async def _try_build_item(
    db: AsyncSession, vocab: Vocab, used_sentence_ids: set[int]
) -> dict | None:
    """A cloze item for `vocab`, or None if it has no usable sentence or
    not enough distractor words."""
    sentences = await vocab_service.get_sentences(db, vocab.word)
    sentence = next((s for s in sentences if s.id not in used_sentence_ids), None)
    if sentence is None:
        return None

    distractor_words = await vocab_service.get_distractor_words(db, vocab)
    if len(distractor_words) < 3:
        return None

    used_sentence_ids.add(sentence.id)
    return _build_cloze_item(sentence, vocab.word, distractor_words)


async def get_sentence_cloze_batch(
    db: AsyncSession,
    source: Literal["kanji", "vocab"],
    jlpt_level: str,
    scope: Literal["exact", "and_below"],
    distribution: Literal["balanced", "challenge"],
    count: int,
    exclude: set[str],
) -> list[dict]:
    """A stateless batch of sentence-cloze items, best-effort up to `count`
    (fewer if not enough candidates have a usable sentence + 3 distractors).
    `source` picks how target words are chosen: directly from vocab, or via
    kanji -> one of that kanji's vocab_words."""
    if source == "vocab":
        return await _vocab_cloze_items(db, jlpt_level, scope, distribution, count, exclude)
    return await _kanji_cloze_items(db, jlpt_level, scope, distribution, count, exclude)
