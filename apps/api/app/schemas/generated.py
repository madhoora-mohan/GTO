# ============================================================
# AUTO-GENERATED — DO NOT EDIT
# Source: api-spec.yaml
# Regenerate: uv run python -m datamodel_code_generator --input ../../api-spec.yaml --input-file-type openapi --output app/schemas/generated.py --target-python-version 3.11 --use-annotated --field-constraints
# ============================================================

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Any
from uuid import UUID

from pydantic import AnyUrl, AwareDatetime, BaseModel, EmailStr, Field


class ApiError(BaseModel):
    detail: Annotated[str, Field(examples=['Not found'])]
    code: Annotated[str | None, Field(examples=['NOT_FOUND'])] = None


class RegisterInput(BaseModel):
    email: Annotated[EmailStr, Field(examples=['user@example.com'])]
    password: Annotated[str, Field(examples=['securepass123'], min_length=8)]


class LoginInput(BaseModel):
    email: Annotated[EmailStr, Field(examples=['user@example.com'])]
    password: Annotated[str, Field(examples=['securepass123'], min_length=8)]


class RefreshResponse(BaseModel):
    access_token: Annotated[
        str, Field(examples=['eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...'])
    ]


class User(BaseModel):
    id: Annotated[UUID, Field(examples=['550e8400-e29b-41d4-a716-446655440000'])]
    email: Annotated[EmailStr, Field(examples=['user@example.com'])]
    created_at: Annotated[AwareDatetime, Field(examples=['2026-01-01T00:00:00Z'])]


class Type(StrEnum):
    hiragana = 'hiragana'
    katakana = 'katakana'


class Category(StrEnum):
    base = 'base'
    dakuten = 'dakuten'
    handakuten = 'handakuten'
    yoon = 'yoon'


class Kana(BaseModel):
    character: Annotated[
        str,
        Field(description='The kana character — also the primary key', examples=['き']),
    ]
    romaji: Annotated[str, Field(examples=['ki'])]
    type: Annotated[Type, Field(examples=['hiragana'])]
    row: Annotated[
        str | None,
        Field(
            description="Which row of the kana chart (e.g. 'k' for ka-row)",
            examples=['k'],
        ),
    ] = None
    col: Annotated[
        str | None,
        Field(
            description="Which column (e.g. 'i' for the i-sound column)", examples=['i']
        ),
    ] = None
    category: Annotated[Category | None, Field(examples=['base'])] = None
    katakana_equivalent: Annotated[
        str | None,
        Field(
            description='For hiragana entries — the katakana version', examples=['キ']
        ),
    ] = None
    hiragana_equivalent: Annotated[
        str | None,
        Field(
            description='For katakana entries — the hiragana version', examples=['き']
        ),
    ] = None
    mnemonic: Annotated[str | None, Field(examples=['Looks like a key'])] = None
    audio_url: Annotated[
        AnyUrl | None, Field(examples=['https://r2.yourdomain.com/audio/kana/ki.mp3'])
    ] = None
    stroke_order_svg_url: Annotated[
        AnyUrl | None, Field(examples=['https://r2.yourdomain.com/kanjivg/kana/き.svg'])
    ] = None


class Component(BaseModel):
    id: Annotated[int, Field(examples=[1])]
    character: Annotated[str, Field(examples=['木'])]
    keyword: Annotated[
        str | None,
        Field(
            description='Short English label used in mnemonic generation',
            examples=['tree'],
        ),
    ] = None
    meaning: Annotated[str | None, Field(examples=['Tree or wood'])] = None
    stroke_count: Annotated[int | None, Field(examples=[4])] = None


class Jlpt(StrEnum):
    N5 = 'N5'
    N4 = 'N4'
    N3 = 'N3'
    N2 = 'N2'
    N1 = 'N1'


class MnemonicUpdateInput(BaseModel):
    mnemonic: Annotated[
        str,
        Field(
            description='The user\'s personal mnemonic. Send empty string "" to clear it and revert to the LLM default.\n',
            examples=['My new axe stands against the tree outside.'],
            max_length=500,
            min_length=0,
        ),
    ]


class MnemonicUpdateResponse(BaseModel):
    character: Annotated[str, Field(examples=['新'])]
    user_mnemonic: Annotated[
        str, Field(examples=['My new axe stands against the tree outside.'])
    ]


class VocabMeaning(BaseModel):
    pos: Annotated[
        list[str] | None,
        Field(description='Part of speech tags from JMdict', examples=[['v1']]),
    ] = None
    definitions: Annotated[
        list[str] | None, Field(examples=[['to eat', 'to live on']])
    ] = None


class FuriganaSegment(BaseModel):
    text: Annotated[str, Field(examples=['食'])]
    furigana: Annotated[
        str | None,
        Field(
            description='Reading for this segment. Null for kana-only segments.',
            examples=['た'],
        ),
    ] = None


class PitchAccent(BaseModel):
    pattern: Annotated[str | None, Field(examples=['LHL'])] = None
    position: Annotated[int | None, Field(examples=[2])] = None
    type: Annotated[str | None, Field(examples=['atamadaka'])] = None


class Sentence(BaseModel):
    id: Annotated[int, Field(description='Tatoeba sentence ID', examples=[1234])]
    japanese: Annotated[str, Field(examples=['私は毎日学校に行きます。'])]
    english: Annotated[str, Field(examples=['I go to school every day.'])]
    jlpt: Annotated[Jlpt | None, Field(examples=['N5'])] = None
    source: Annotated[str | None, Field(examples=['tatoeba'])] = 'tatoeba'


class PaginatedKana(BaseModel):
    data: list[Kana]
    total: Annotated[int, Field(examples=[208])]
    page: Annotated[int, Field(examples=[1])]
    page_size: Annotated[int, Field(examples=[20])]


class PaginatedSentence(BaseModel):
    data: list[Sentence]
    total: Annotated[int, Field(examples=[50000])]
    page: Annotated[int, Field(examples=[1])]
    page_size: Annotated[int, Field(examples=[20])]


class PaginatedComponent(BaseModel):
    data: list[Component]
    total: Annotated[int, Field(examples=[253])]
    page: Annotated[int, Field(examples=[1])]
    page_size: Annotated[int, Field(examples=[20])]


class AuthResponse(BaseModel):
    access_token: Annotated[
        str, Field(examples=['eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...'])
    ]
    user: User


class Kanji(BaseModel):
    character: Annotated[
        str,
        Field(
            description='The kanji character — also the primary key', examples=['新']
        ),
    ]
    unicode_hex: Annotated[str | None, Field(examples=['065b0'])] = None
    meanings: Annotated[list[str] | None, Field(examples=[['new', 'neo-']])] = None
    onyomi: Annotated[list[str] | None, Field(examples=[['シン']])] = None
    kunyomi: Annotated[
        list[str] | None, Field(examples=[['あたら.しい', 'あら.た']])
    ] = None
    nanori: Annotated[list[str] | None, Field(examples=[['あらた']])] = None
    jlpt: Annotated[Jlpt | None, Field(examples=['N2'])] = None
    grade: Annotated[
        int | None,
        Field(
            description='Japanese school grade (1–6 elementary, 8 secondary)',
            examples=[2],
        ),
    ] = None
    stroke_count: Annotated[int | None, Field(examples=[13])] = None
    frequency: Annotated[
        int | None,
        Field(description='Frequency rank out of 2500 most-used kanji', examples=[56]),
    ] = None
    classical_radical_number: Annotated[int | None, Field(examples=[69])] = None
    classical_radical_char: Annotated[str | None, Field(examples=['斤'])] = None
    stroke_order_svg_url: Annotated[
        AnyUrl | None, Field(examples=['https://r2.yourdomain.com/kanjivg/065b0.svg'])
    ] = None
    mnemonic: Annotated[
        str | None,
        Field(
            description='LLM-generated default mnemonic',
            examples=[
                "A person stands next to a tree and swings an axe — they're clearing land to build something NEW.\n"
            ],
        ),
    ] = None
    user_mnemonic: Annotated[
        str | None,
        Field(
            description="The authenticated user's personal mnemonic override. Null means the user has not written one — show mnemonic instead. Only present on GET /kanji/{character} (requires auth).\n",
            examples=['My new axe stands against the tree outside.'],
        ),
    ] = None
    components: Annotated[
        list[Component] | None,
        Field(
            description='Visual components this kanji is made of. Only included on GET /kanji/{character} (detail view). Not included in list responses for performance.\n'
        ),
    ] = None
    sentences: Annotated[
        list[Sentence] | None,
        Field(
            description='Example sentences containing this kanji. Only included on GET /kanji/{character} (detail view). Not included in list responses.\n'
        ),
    ] = None


class Vocab(BaseModel):
    id: Annotated[
        str, Field(description='JMdict entry sequence number', examples=['1578850'])
    ]
    word: Annotated[str, Field(examples=['食べる'])]
    reading: Annotated[str, Field(examples=['たべる'])]
    romaji: Annotated[str | None, Field(examples=['taberu'])] = None
    meanings: list[VocabMeaning]
    furigana: list[FuriganaSegment] | None = None
    jlpt: Annotated[Jlpt | None, Field(examples=['N5'])] = None
    frequency: Annotated[
        int | None,
        Field(
            description='Raw frequency marker from JMdict (1 = most common)',
            examples=[1],
        ),
    ] = None
    frequency_rank: Annotated[
        int | None,
        Field(
            description='Frequency rank from Kanjium (1 = most common overall)',
            examples=[312],
        ),
    ] = None
    pitch_accent: PitchAccent | None = None
    is_common: Annotated[
        bool | None,
        Field(
            description='True if tagged ichi1/news1/spec1 in JMdict', examples=[True]
        ),
    ] = None
    tags: Annotated[dict[str, Any] | None, Field(examples=[{'dialect': 'kansai'}])] = (
        None
    )
    sentences: Annotated[
        list[Sentence] | None,
        Field(
            description='Example sentences for this word. Only included on GET /vocab/{id} (detail view). Not included in list responses.\n'
        ),
    ] = None


class PaginatedKanji(BaseModel):
    data: list[Kanji]
    total: Annotated[int, Field(examples=[2200])]
    page: Annotated[int, Field(examples=[1])]
    page_size: Annotated[int, Field(examples=[20])]


class PaginatedVocab(BaseModel):
    data: list[Vocab]
    total: Annotated[int, Field(examples=[10000])]
    page: Annotated[int, Field(examples=[1])]
    page_size: Annotated[int, Field(examples=[20])]
