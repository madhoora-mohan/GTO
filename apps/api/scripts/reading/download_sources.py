"""
Step 2.2 — Download raw data for the reading-comprehension pipeline.

Run from apps/api/:
    uv run scripts/reading/download_sources.py

What this downloads (Track A, the "extracted from real text" track):
- JaQuAD  — a Japanese reading-comprehension dataset built from Wikipedia
            articles + question/answer pairs (CC BY-SA 3.0 license).
- JSQuAD  — the Japanese half of JGLUE, same idea as JaQuAD: Wikipedia
            passages + Q&A pairs (CC BY-SA 4.0 license).

JaQuAD's HuggingFace repo only ships a legacy "dataset loading script"
(JaQuAD.py), which the `datasets` library no longer supports running for
security reasons (arbitrary code execution). So instead of `load_dataset()`,
we list the repo's files via `huggingface_hub` and download the raw SQuAD-
format JSON shards directly (data/train/*.json, data/dev/*.json) — same
data, just fetched as plain files instead of through the disabled script
loader.

JSQuAD ships proper parquet files, so `load_dataset()` works normally there
and we use `save_to_disk()` to cache it in HuggingFace's Arrow format for
fast reloading by normalize.py.

Aozora Bunko (public-domain classic Japanese literature) is NOT downloaded
here — it's a much bigger git repository, so it's cloned manually (see the
docstring at the bottom of this file). This script only handles the two
HuggingFace QA datasets.

Idempotent: re-running just re-downloads/re-overwrites the same files —
harmless, no data loss.
"""

import json
import os

from datasets import load_dataset
from huggingface_hub import HfApi, hf_hub_download

RAW_DIR = "data/raw/reading"
os.makedirs(RAW_DIR, exist_ok=True)

print("Downloading JaQuAD (CC BY-SA 3.0)...")
JAQUAD_REPO = "SkelterLabsInc/JaQuAD"
jaquad_dir = f"{RAW_DIR}/jaquad"
os.makedirs(jaquad_dir, exist_ok=True)

api = HfApi()
jaquad_json_files = [
    f for f in api.list_repo_files(JAQUAD_REPO, repo_type="dataset")
    if f.startswith("data/") and f.endswith(".json")
]
for repo_path in jaquad_json_files:
    local_path = hf_hub_download(JAQUAD_REPO, repo_path, repo_type="dataset")
    # repo_path looks like "data/train/jaquad_train_0000.json" — flatten
    # train/dev into the filename itself so all shards land in one folder.
    out_name = repo_path.replace("data/", "").replace("/", "_")
    with open(local_path, encoding="utf-8") as src, open(f"{jaquad_dir}/{out_name}", "w", encoding="utf-8") as dst:
        json.dump(json.load(src), dst, ensure_ascii=False)
print(f"  Saved {len(jaquad_json_files)} shards to {jaquad_dir}/")

print("Downloading JSQuAD (CC BY-SA 4.0, part of JGLUE)...")
jsquad = load_dataset("sbintuitions/JSQuAD")
jsquad.save_to_disk(f"{RAW_DIR}/jsquad")
print(f"  Saved to {RAW_DIR}/jsquad")

print("\nDone with JaQuAD/JSQuAD.")
print("Aozora Bunko is NOT downloaded by this script — clone it manually:")
print("  git clone --depth 1 https://github.com/aozorabunko/aozorabunko.git data/raw/reading/aozora_raw")
print("Then manually pick 30-50 short works from data/raw/reading/aozora_raw/cards/")
print("and list their file paths (one per line) in data/raw/reading/aozora_selected.txt.")
print("This selection step is deliberately manual — see the handoff doc, Step 2.2.")
