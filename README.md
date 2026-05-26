# GTO

A Japanese learning app — kana, kanji, vocabulary, and example sentences across all JLPT levels (N5–N1).

Monorepo: one repo, three apps, independent deployments.

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
| Backend | FastAPI (Python), Render |
| Database | Neon (PostgreSQL) |
| Storage | Cloudflare R2 (SVGs, audio) |
| Web | React, TanStack Router, Vercel / CF Pages |
| Mobile | React Native, Expo, EAS |
| Shared | Zod, TypeScript path aliases |

## Database

| Table | Contents |
|---|---|
| `kana` | Hiragana + Katakana (~208 characters) |
| `kanji` | 2,200 JLPT kanji with readings, meanings, stroke count, frequency, mnemonics |
| `component` | ~253 kanji radicals with English keywords |
| `kanji_component` | Kanji → radical decomposition |
| `vocab` | ~10,000 JLPT words with readings, furigana, pitch accent, frequency |
| `sentence` | ~50,000 Japanese/English sentence pairs |
| `vocab_sentence` | Vocab → sentence links |
| `kanji_sentence` | Kanji → sentence links |

## Setup

```bash
# Install dependencies (from repo root)
bun install

# Backend
cd apps/api
pip install fastapi uvicorn sqlalchemy alembic psycopg2-binary python-dotenv
export DATABASE_URL="postgresql://user:password@host/neondb"
uvicorn main:app --reload

# Web
cd apps/web
bun dev

# Mobile
cd apps/mobile
bunx expo start
```
