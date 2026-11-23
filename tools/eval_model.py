"""Quick check of the local GGUF model: loads on GPU, returns valid JSON, matches labels.

    python tools/eval_model.py [n_samples]

Note: samples come from backend/data/sft_data.jsonl (the training set), so this checks
that the model learned the format and the decisions, not how it generalises.
"""
import json
import os
import random
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))
from local_llm import MODEL_PATH, get_llm  # noqa: E402

n = int(sys.argv[1]) if len(sys.argv) > 1 else 40
rows = [json.loads(l) for l in open(os.path.join(ROOT, "backend", "data", "sft_data.jsonl"), encoding="utf-8")]
random.seed(1)
sample = random.sample(rows, n)

print("model:", MODEL_PATH, round(os.path.getsize(MODEL_PATH) / 1e9, 2), "GB")
t0 = time.time()
llm = get_llm()
print(f"loaded in {time.time() - t0:.1f}s")

valid = type_ok = exact = 0
from collections import Counter
pairs = Counter()
times = []
for r in sample:
    sys_msg, user, target = (m["content"] for m in r["messages"])
    prompt = f"<|im_start|>system\n{sys_msg}<|im_end|>\n<|im_start|>user\n{user}<|im_end|>\n<|im_start|>assistant\n"
    t = time.time()
    out = llm(prompt, max_tokens=160, temperature=0.1, stop=["<|im_end|>", "<|im_start|>"])["choices"][0]["text"].strip()
    times.append(time.time() - t)
    tgt = json.loads(target)
    try:
        got = json.loads(out)
        valid += 1
    except json.JSONDecodeError:
        continue
    pairs[(tgt.get("type"), got.get("type"))] += 1
    if got.get("type") == tgt.get("type"):
        type_ok += 1
        if got == tgt:
            exact += 1

print(f"\nsamples          : {n}")
print(f"valid JSON       : {valid}/{n}")
print(f"same action type : {type_ok}/{n}")
print(f"exact match      : {exact}/{n}")
print("label -> model:", pairs.most_common(12))
print(f"avg latency      : {sum(times) / len(times):.2f}s  (max {max(times):.2f}s)")
