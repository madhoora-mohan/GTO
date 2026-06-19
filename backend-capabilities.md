# GTO Backend Capabilities

Sources: `api-spec.yaml` (local, working tree) cross-checked against the live
deployment at `https://gto-backend.onrender.com` (its auto-generated
`/openapi.json`, plus live `curl` calls against every endpoint as of
2026-06-20).

Base URL (live): `https://gto-backend.onrender.com`
Auth: Bearer JWT access token (15 min) + HttpOnly refresh-token cookie (30 days). See `api-spec.yaml` header comments for the full token-refresh flow — not repeated here.

---

## 1. Status at a glance

| Domain | Spec'd | Live | Notes |
|---|---|---|---|
| Auth | ✅ | ✅ | register/login/refresh/logout all present live |
| Kana | ✅ | ✅ | matches spec exactly |
| Kanji | ✅ | ✅ | matches spec exactly, including auth-gated detail view |
| Vocab | ✅ | ✅ | matches spec exactly |
| Sentences | ✅ | ✅ | matches spec exactly |
| Components (radicals) | ✅ | ✅ | matches spec exactly |
| Files (R2 upload) | ✅ | ✅ (schema only verified; not exercised against real R2) |
| **Reading comprehension** | ✅ | ❌ **NOT LIVE** | Fully built in the local working tree (router wired into `main.py`, service, models, migration) but the deployed instance's `/openapi.json` has no `/reading/*` routes — it's running an older build. Hitting `/reading/passages` on the live URL returns a generic 404, not the app's `not_found` shape. |
| `/study/*` (SRS/flashcards) | ❌ explicitly deferred in spec | ❌ | Spec footer states this is deferred — no design yet, not a deployment gap. |

A `/health` endpoint exists live (`{"status":"ok"}`) — useful for uptime checks, not in `api-spec.yaml`.

---

## 2. Auth

### `POST /auth/register`
- **Body:** `{ email: string, password: string (min 8) }`
- **Returns `201`:** `AuthResponse { access_token: string, user: User }`
  - `User { id: string(uuid), email: string, created_at: string(date-time) }` — no nullable fields.
- Sets refresh token as an HttpOnly cookie; never appears in the body.
- **Errors:** `409` email already registered, `422` validation.
- **Frontend use:** sign-up flow. Store `access_token` in memory only (never localStorage). The cookie is handled by the browser/native cookie store automatically.

### `POST /auth/login`
- **Body:** `{ email, password }`
- **Returns `200`:** same `AuthResponse` shape as register.
- **Errors:** `401` invalid credentials.

### `POST /auth/refresh`
- No body — refresh cookie sent automatically.
- **Returns `200`:** `RefreshResponse { access_token: string }`. Rotates the refresh cookie too.
- **Errors:** `401` cookie missing/expired/revoked.
- **Frontend use:** call proactively when the access token JWT's `exp` is <5 min away, and once on app start to silently restore a session.

### `POST /auth/logout`
- No body. **Returns `204`**, clears the refresh cookie server-side.
- **Errors:** `401` no valid cookie.
- **Frontend use:** client must also drop the in-memory access token.

Confirmed live: registered a throwaway test user and exercised the full register → token → authenticated request chain successfully.

---

## 3. Kana

### `GET /kana`
- **Query params:** `page` (int, default 1), `page_size` (int, default 20, max 100 — confirmed live: `page_size=101` → `422`), `type` (`hiragana`\|`katakana`), `category` (`base`\|`dakuten`\|`handakuten`\|`yoon`).
- **Returns:** `PaginatedKana { data: Kana[], total, page, page_size }`.
- Live `total` is **214**, not the spec's example value of 208 (just a stale example, not a real mismatch — the example was never meant to be exact).

**`Kana` fields:**
| Field | Type | Nullable | Notes |
|---|---|---|---|
| `character` | string | no | primary key |
| `romaji` | string | no | |
| `type` | enum `hiragana`/`katakana` | no | |
| `row` | string | **yes** | consonant group; null for yōon and ん/ン. Live data also returns `"vowel"` for あ/い/う/え/お (not documented in spec's example but consistent with the "derived from romaji" description) |
| `col` | string | yes | vowel column |
| `category` | enum | no | |
| `katakana_equivalent` | string | yes | only set on hiragana rows |
| `hiragana_equivalent` | string | yes | only set on katakana rows (live spot-check returned `null` for hiragana row, as expected) |
| `mnemonic` | string | yes | **currently always `null` in live data** — not yet populated |
| `audio_url` | string (uri) | yes | **currently always `null` in live data** |
| `stroke_order_svg_url` | string (uri) | yes | **currently always `null` in live data** |

- **Frontend use:** drives a kana chart/grid (filter by `type`+`category` for hiragana-only or yōon-only views) and flashcard drilling. Audio/SVG/mnemonic fields are wired up in the schema but not yet seeded — don't build UI that assumes they're populated yet for kana (contrast with kanji, where `mnemonic`/`stroke_order_svg_url` ARE populated).

### `GET /kana/{character}`
- Path param: the kana character itself, URL-encoded (e.g. `き` → `%E3%81%8D`).
- **Returns `200`:** single `Kana` object (same shape as above).
- **Errors:** `404` if not found.
- **Frontend use:** detail view from a kana grid tap.

---

## 4. Kanji

### `GET /kanji`
- Public, no auth.
- **Query params:** `page`, `page_size`, `jlpt` (exact level), `jlpt_max` (this level or easier; mutually exclusive with `jlpt` — confirmed live: supplying both → `422`), `grade` (1–8), `stroke_count` (int).
- **Returns:** `PaginatedKanji`. Does **not** include `components`, `sentences`, `vocab_words`, or `user_mnemonic` — list rows are the lean shape for performance.
- Live `total` is **10,384** — much larger than the spec's example value of 2,200 (again just a stale doc example, not a discrepancy worth fixing in app behavior, but worth fixing in the spec's example if it's meant to communicate real scale).

**`Kanji` fields (list view):**
| Field | Type | Nullable | Notes |
|---|---|---|---|
| `character` | string | no | primary key |
| `unicode_hex` | string | no | |
| `meanings` | string[] | no | |
| `onyomi` | string[] | yes | |
| `kunyomi` | string[] | yes | |
| `nanori` | string[] | yes | |
| `jlpt` | enum N5–N1 | yes | |
| `grade` | int | yes | 1–6 elementary, 8 = secondary |
| `stroke_count` | int | no | |
| `frequency` | int | yes | rank out of top 2500 |
| `classical_radical_number` | int | yes | Kangxi radical # |
| `stroke_order_svg_url` | string (uri) | yes | **populated live**, e.g. `https://pub-362b3afdf5f6499ca6d013cfdf72ad2a.r2.dev/svg/kanji/04eba.svg` — note this is a real Cloudflare R2 public bucket URL, not the placeholder `r2.yourdomain.com` shown in spec examples |
| `mnemonic` | string | yes | LLM-generated default — **populated live** |

`components`, `sentences`, `vocab_words`, `user_mnemonic` are absent (not just null) from list rows.

### `GET /kanji/{character}` — **requires auth**
- Confirmed live: no `Authorization` header → `401 {"error":"http_error","message":"Not authenticated"}`. Bad token → `401 {"error":"http_error","message":"Could not validate credentials"}`. Note both use the generic `http_error` code rather than something like `unauthorized` — worth knowing if the frontend ever branches on `error` string rather than just the HTTP status.
- **Returns:** full `Kanji` object including:
  - `user_mnemonic` (string, nullable) — the authenticated user's override; null means "show `mnemonic`."
  - `components` — array of `Component` (id, character, keyword, meaning, stroke_count), the visual radicals making up the kanji.
  - `sentences` — up to 10 `Sentence` objects, ordered by sentence ID ascending.
  - `vocab_words` — up to 20 `KanjiVocabEntry` objects: `{ id, word, reading, romaji?, meanings: VocabMeaning[], jlpt?, is_common?, reading_type? ('on'|'kun'|null) }`, ordered by JLPT (N5 first, null last) → `is_common` → vocab id. Frontend is expected to group these by `reading_type` itself.
- Confirmed live end-to-end (registered a user, fetched `新` authenticated): full payload including 5 components (亠/斤/木/立/辛), 10 sentences, vocab words with `reading_type` populated correctly.
- **Frontend use:** the kanji detail/study page. Because this is the only endpoint that returns components/sentences/vocab, any "kanji deep dive" screen needs the user to be logged in — there's no anonymous detail view, only the list.

### `PATCH /kanji/{character}/mnemonic` — **requires auth**
- **Body:** `{ mnemonic: string (0–500 chars) }`. Empty string clears the override and reverts to the LLM default.
- **Returns `200`:** `{ character: string, user_mnemonic: string|null }`.
- Confirmed live: PATCH with `{"mnemonic":"test mnemonic"}` on `新` → `{"character":"新","user_mnemonic":"test mnemonic"}`.
- **Frontend use:** "write your own mnemonic" editor on the kanji detail page.

---

## 5. Vocabulary

### `GET /vocab`
- Public, no auth.
- **Query params:** `page`, `page_size`, `jlpt`, `jlpt_max`, `is_common` (bool), `search` (partial match on word or reading).
- **Returns:** `PaginatedVocab`. Live `total` **7,645** (vs. spec's example 10,000 — example only). Confirmed `is_common=true` filter works live (returns 6,462 of the 7,645).
- Confirmed `search=食` live → 22 matches including 食べる, 食べ物.

**`Vocab` fields (list view):**
| Field | Type | Nullable | Notes |
|---|---|---|---|
| `id` | string | no | JMdict sequence number |
| `word` | string | no | |
| `reading` | string | no | |
| `romaji` | string | yes | |
| `meanings` | `VocabMeaning[]` | no | each is `{ pos: string[]\|null, definitions: string[]\|null }` |
| `furigana` | `FuriganaSegment[]` | yes | each `{ ruby: string, rt: string\|null }`; populated in list view (unlike spec's framing that implies it's detail-only — confirmed live list rows DO include furigana) |
| `jlpt` | enum | yes | |
| `is_common` | bool | yes | ichi1/news1/spec1 tag |
| `sentences` | always `null` in list view | yes | only populated on detail fetch |

### `GET /vocab/{id}`
- Path param: JMdict sequence number, e.g. `1578850`.
- **Returns:** full `Vocab` including `sentences` (up to 10, ordered by sentence ID). Confirmed live for `1578850` (行く) — 12 `VocabMeaning` entries and a populated `sentences` array.
- **Errors:** `404` if not found.
- **Frontend use:** `/vocab` + `search` powers a vocab search/browse screen; `/vocab/{id}` is the word detail page with example sentences. `furigana` lets the frontend render ruby text without needing client-side kuroshiro for vocab specifically (sentences still rely on client-side furigana per the spec's reading-passage notes).

---

## 6. Sentences

### `GET /sentences`
- Public. **Query params:** `page`, `page_size`, `search` (partial match on Japanese text).
- **Returns:** `PaginatedSentence`. Live `total` is **232,584** (spec example says 50,000 — way off, worth updating if anyone treats that number as real capacity planning input).

**`Sentence` fields:** `{ id: int, japanese: string, english: string }` — all required, no nullable fields. Simplest model in the API.

### `GET /sentences/{id}`
- Path param: Tatoeba sentence ID (int).
- **Returns:** single `Sentence`. **Errors:** `404`.
- **Frontend use:** standalone sentence lookup/search, and the underlying data source reused inline inside `Kanji.sentences` / `Vocab.sentences`. A sentence-of-the-day or example-sentence search feature could use this directly.

---

## 7. Components (radicals)

### `GET /components`
- Public. **Query params:** `page`, `page_size` only — no filters.
- **Returns:** `PaginatedComponent`. Live `total` **253** (matches spec example exactly).

**`Component` fields:** `{ id: int, character: string, keyword: string, meaning: string, stroke_count: int }` — all required.

### `GET /components/{id}`
- Path param: integer id. **Errors:** `404` (confirmed live: `id=1` doesn't exist → `{"error":"not_found","message":"Component '1' not found"}` — ids start at 2 in the live data, gap likely from seed data cleanup).
- **Frontend use:** standalone radical reference page, and the building blocks shown inline in `Kanji.components` on the kanji detail view. Not much value as a standalone browse feature on its own — mostly support data for kanji mnemonics.

---

## 8. Reading comprehension — **NOT LIVE**

Fully implemented in the local working tree: `app/models/reading_passage.py`, `app/models/reading_question.py`, `app/routers/reading.py`, `app/services/reading_service.py`, and a migration (`aeee3884bdea_add_reading_comprehension_tables.py`). The router is wired into `main.py` (`app.include_router(reading.router, prefix="/reading", ...)`), and `api-spec.yaml` has the full spec already written. **None of this is on the deployed instance** — its `/openapi.json` has no `/reading/*` paths, and hitting the live URLs returns the framework's generic 404, not the app's structured `{"error":"not_found",...}` shape (i.e. the live instance is running a build from before this feature was added).

Once deployed, the spec describes:

### `GET /reading/passages`
- **Query params:** `page`, `page_size`, `jlpt_level`.
- **Returns:** `PaginatedReadingPassage`. List rows omit `passage_text`, `furigana_segments`, `english_translation`, `questions` (avoids an R2 fetch per row).

**`ReadingPassage` fields:**
| Field | Type | Nullable | Notes |
|---|---|---|---|
| `id` | int | no | |
| `title` | string | yes | |
| `jlpt_level` | enum N5–N1 | no | |
| `difficulty_score` | float | no | raw jReadability score — lower = harder |
| `word_count` | int | no | |
| `source` | enum `jaquad`/`jsquad`/`aozora`/`llm_qwen3.5` | no | |
| `passage_text` | string | yes | detail-only; fetched from R2 via `content_key`, never stored in Postgres |
| `furigana_segments` | `FuriganaSegment[]` | yes | detail-only; only populated for `source=aozora` — frontend falls back to client-side kuroshiro otherwise |
| `english_translation` | string | yes | detail-only |
| `questions` | `ReadingQuestion[]` | yes | detail-only |

### `GET /reading/passages/{id}`
- **Returns:** full `ReadingPassage` with all detail-only fields populated, including the nested `questions` array (each question's own text/options/answer/explanation are also content fetched via R2 at request time, per `reading_service.get_question_content`).

**`ReadingQuestion` fields:** `{ id, passage_id, question_order, question_text, options: string[4], correct_answer, explanation }` — all required, no nullable fields.

**Frontend use (once deployed):** a JLPT-style reading comprehension practice mode — list/filter passages by level, then a quiz screen per passage with 4-option multiple choice questions and explanations.

---

## 9. Files (R2 uploads)

Schema-verified against live `/openapi.json` (matches spec exactly); not exercised end-to-end against real R2 since that requires real file bytes and a presigned URL round-trip.

### `POST /files/presign` — requires auth
- **Body:** `{ filename, mime_type, size_bytes }`. `size_bytes` validated against `MAX_FILE_SIZE_BYTES` (10MB) server-side.
- **Returns `200`:** `{ object_key: string, upload_url: string(uri), expires_in: int (seconds) }`.
- **Errors:** `401`, `422` (oversized file or bad input).

### `POST /files/confirm` — requires auth
- **Body:** `{ object_key, filename, mime_type, size_bytes }` — same `object_key` returned by presign.
- **Returns `201`:** `FileMetadata { id: uuid, object_key, filename, mime_type, size_bytes, uploaded_by: uuid, created_at: date-time }` — all required, no nullable fields.
- **Errors:** `401`, `422`.

**Frontend use:** generic attachment upload (e.g. "upload your own mnemonic image" mentioned in the spec's example filenames). Flow: client requests a presigned URL, PUTs bytes directly to R2 (bypassing the API), then confirms so the API can record metadata. Bytes never touch the backend server.

---

## 10. Cross-cutting notes

**Error shape.** Every non-2xx response is normalized server-side (see `app/core/errors.py`) to `{ error: string, message: string }`, matching the spec's `ApiError`. In practice the `error` field is often the generic `"http_error"` (e.g. both the "missing token" and "bad token" cases on `/kanji/{character}` use `"http_error"` rather than something like `"unauthorized"`) — don't build frontend logic that branches on specific `error` string values for auth failures; use the HTTP status code instead. `404`s for resource lookups (kanji, vocab, components) do use specific codes like `"not_found"`.

**Pagination.** Consistent across every list endpoint: `{ data, total, page, page_size }`. `page` is 1-indexed, `page_size` max 100 (confirmed live — `page_size=101` → `422`). No cursor-based pagination anywhere.

**Live R2 bucket.** SVG/image URLs in live responses point to a real Cloudflare R2 public bucket (`https://pub-362b3afdf5f6499ca6d013cfdf72ad2a.r2.dev/...`), not the `r2.yourdomain.com` placeholder host shown in the spec's examples — expected, since spec examples are illustrative only.

**Kana media fields are stubbed.** `mnemonic`, `audio_url`, and `stroke_order_svg_url` on `Kana` are all `null` in every live row checked. The schema supports them but no seed data has populated them yet — don't design a kana UI around audio/SVG being available today.

**Spec example numbers are stale, not contractual.** `total` examples in the spec (kana 208, kanji 2200, vocab 10000, sentences 50000) are all off from live counts (214 / 10,384 / 7,645 / 232,584) by a wide margin. They're illustrative OpenAPI examples, not assertions about real data volume — useful to know so nobody mistakes them for capacity figures.

**Deferred (by design).** `/study/*` (SRS scheduling, flashcard review sessions, SM-2 algorithm) is explicitly called out in the spec as deferred pending a separate design pass — not a deployment gap, just not designed yet.
