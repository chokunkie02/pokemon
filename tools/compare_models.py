"""Compare two GGUF models on the same decision samples.

    python tools/compare_models.py OLD.gguf NEW.gguf [n]

Uses the 8% held-out split the v2 notebook kept aside (same seed), rebuilt here with
the same `datasets.train_test_split`, if the `datasets` package is installed; otherwise
falls back to a fixed random sample of the whole set (which favours the old model,
since it was trained on everything).
"""
import json
import os
import random
import sys
import time
from collections import Counter

from llama_cpp import Llama

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "backend", "data", "sft_data.jsonl")


def load_samples(n):
    try:
        from datasets import load_dataset
        split = load_dataset("json", data_files=DATA, split="train").train_test_split(test_size=0.08, seed=3407)
        rows = [r for r in split["test"]]
        return rows[:n], f"held-out split ({len(rows)} rows, never seen by v2)"
    except ImportError:
        rows = [json.loads(l) for l in open(DATA, encoding="utf-8")]
        random.seed(7)
        return random.sample(rows, n), "random sample of full set (v1 trained on all of it)"


def evaluate(path, samples):
    llm = Llama(model_path=path, n_ctx=4096, n_batch=512, n_gpu_layers=-1, verbose=False)
    valid = same_type = exact = 0
    confusions = Counter()
    times = []
    for r in samples:
        sys_msg, user, target = (m["content"] for m in r["messages"])
        prompt = f"<|im_start|>system\n{sys_msg}<|im_end|>\n<|im_start|>user\n{user}<|im_end|>\n<|im_start|>assistant\n"
        t = time.time()
        out = llm(prompt, max_tokens=160, temperature=0.0, stop=["<|im_end|>", "<|im_start|>"])["choices"][0]["text"].strip()
        times.append(time.time() - t)
        tgt = json.loads(target)
        try:
            got = json.loads(out)
        except json.JSONDecodeError:
            confusions[(tgt.get("type"), "INVALID")] += 1
            continue
        valid += 1
        if got.get("type") == tgt.get("type"):
            same_type += 1
            exact += got == tgt
        else:
            confusions[(tgt.get("type"), got.get("type"))] += 1
    del llm
    return dict(valid=valid, same_type=same_type, exact=exact,
                latency=sum(times) / len(times), confusions=confusions.most_common(5))


def main():
    old, new = sys.argv[1], sys.argv[2]
    n = int(sys.argv[3]) if len(sys.argv) > 3 else 130
    samples, desc = load_samples(n)
    n = len(samples)
    print(f"samples: {n} — {desc}\n")
    res = {}
    for name, path in (("old (v1)", old), ("new (v2)", new)):
        res[name] = evaluate(path, samples)
    print(f"{'':16}{'old (v1)':>12}{'new (v2)':>12}")
    for key, label in (("valid", "valid JSON"), ("same_type", "same action"), ("exact", "exact match")):
        a, b = res["old (v1)"][key], res["new (v2)"][key]
        print(f"{label:16}{a:>7}/{n:<4}{b:>7}/{n:<4}   ({a / n:.0%} -> {b / n:.0%})")
    print(f"{'avg latency':16}{res['old (v1)']['latency']:>11.2f}s{res['new (v2)']['latency']:>11.2f}s")
    for name in res:
        print(f"\n{name} top mistakes (label -> model):", res[name]["confusions"])


if __name__ == "__main__":
    main()
