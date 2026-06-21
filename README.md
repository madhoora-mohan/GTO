# GTO

A Japanese learning app — kana, kanji, vocabulary, example sentences, and
JLPT-style reading comprehension across all levels (N5–N1). Includes user
accounts (personal kanji mnemonics) and a Practice tab (flashcard-style
batches, sentence cloze, an interlocking vocab crossword).

Monorepo: one repo, three apps, independent deployments.

API live at `https://gto-backend.onrender.com` (Swagger UI at `/docs`).

## Structure

```
apps/
  api/       FastAPI backend → Render
  web/       React frontend → Vercel / Cloudflare Pages
  mobile/    React Native (Expo) → EAS
packages/
  shared/    API types, Zod schemas, validation — consumed by web and mobile
```

## Stack

| Layer | Tech |
|---|---|
| Monorepo | Bun workspaces |
| Backend | FastAPI (Python), uv, Render |
| Database | Neon (PostgreSQL) |
| Storage | Cloudflare R2 (SVGs, presigned uploads, reading-comprehension content) |
| Web | React, TanStack Router, Vercel / CF Pages |
| Mobile | React Native, Expo, EAS |
| Shared | Zod, TypeScript path aliases |
| API contract | OpenAPI spec-first (`api-spec.yaml`) — generates both Pydantic and TypeScript types |

## API overview

Spec-first: `api-spec.yaml` at repo root is the single source of truth. See
`docs/roadmap.md` for the full endpoint table and design rationale, or
`/docs` on the live API for interactive Swagger UI.

Two-token auth (short-lived JWT access token + HttpOnly-cookie refresh
token, see `api-spec.yaml` header comments for the full flow). Current auth
posture:

| Domain | List | Detail |
|---|---|---|
| Kana | Public | Public |
| Kanji | Public | **Bearer required** (returns `user_mnemonic`) |
| Vocab | Public | **Bearer required** |
| Sentences | Public | Public |
| Components (radicals) | Public | Public |
| Reading comprehension | Public | **Bearer required** |
| Practice (`practice-batch`, `crossword`, `sentence-cloze`) | — | **Bearer required** (Practice tab requires login app-wide) |
| Files (R2 uploads) | — | **Bearer required** |
| `/users/me/mnemonics` | — | **Bearer required** |

Vocab and Kanji detail are intentionally gated for different reasons: Kanji
because `user_mnemonic` is genuinely user-specific data; Vocab purely to
keep a public, indexable, highly-linkable detail page from becoming a
crawl-traffic problem on free-tier hosting. List/browse endpoints across
every domain stay public for discovery without an account.

Practice endpoints are stateless — no session or score is persisted
server-side; the frontend manages session state entirely client-side.

Deferred: `/study/*` (SRS / spaced-repetition flashcard sessions) — design
not finalised.

## Database

| Table | Contents |
|---|---|
| `kana` | Hiragana + Katakana (214 characters) |
| `kanji` | 10,384 kanji (2,136 JLPT-tagged: N5 103 · N4 181 · N3 386 · N2 393 · N1 1,073) with readings, meanings, stroke count, frequency, mnemonics |
| `component` | 253 kanji radicals with English keywords |
| `kanji_component` | Kanji → radical decomposition |
| `vocab` | 7,645 JLPT words with readings, furigana, romaji, meanings |
| `sentences` | 232,584 Japanese/English sentence pairs (Tatoeba), GIN trigram-indexed on `japanese` for substring search |
| `kanji_sentence` | Kanji → sentence links |
| `kanji_vocab` | Kanji → vocab links with on/kun reading type |
| `reading_passages` | 328 JLPT-leveled reading comprehension passages (metadata in Neon; passage text/translation/furigana fetched from R2 at request time) |
| `reading_questions` | Multiple-choice comprehension questions per passage |
| `users` | Accounts (email + bcrypt password hash) |
| `refresh_tokens` | Revocable refresh tokens for the two-token auth system |
| `user_mnemonics` | Per-user personal kanji mnemonic overrides |
| `files` | Metadata for presigned R2 uploads |

## Setup

```bash
# Install dependencies (from repo root)
bun install

# Backend
cd apps/api
uv sync
cp .env-example .env   # fill in DATABASE_URL, JWT_SECRET, R2_* creds, CORS_ORIGINS
uv run uvicorn app.main:app --reload
# Swagger UI: http://localhost:8000/docs

# Web
cd apps/web
bun dev

# Mobile
cd apps/mobile
bunx expo start
```

Required backend env vars (see `apps/api/app/core/config.py`):
`DATABASE_URL`, `JWT_SECRET`, `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`,
`R2_SECRET_ACCESS_KEY`, `R2_BUCKET`, `R2_ENDPOINT`, `R2_PUBLIC_URL`,
`CORS_ORIGINS`. `SENTRY_DSN` is optional — error tracking is silently
disabled if unset.

After editing `api-spec.yaml`, regenerate both generated-types files before
implementing against them:

```bash
# Pydantic — from apps/api/
uv run python -m datamodel_code_generator \
  --input ../../api-spec.yaml --input-file-type openapi \
  --output app/schemas/generated.py \
  --target-python-version 3.11 --use-annotated --field-constraints

# TypeScript — from packages/shared/
bunx openapi-typescript ../../api-spec.yaml --output src/types/api.generated.ts
```
