# Pocket Duelist AI Simulation

A Neuro-Symbolic card-game AI: a rule-based engine scores the legal moves, and a fine-tuned
**Qwen2.5-3B** (QLoRA → GGUF `q4_k_m`, run locally with `llama-cpp-python`) picks among the top
options. Guardrails fall back to the rule-based top move whenever the model output is invalid.

```
backend/    FastAPI game engine + AI agent (ai_agent.py, local_llm.py)
  data/     training data (sft_data.jsonl = 1,616 ChatML examples)
frontend/   React + Vite UI
models/     put the .gguf model here (not in git)
training/   train_colab.ipynb — retrain the model on a free Colab T4
start.py    runs backend + frontend together
```

## Run

1. Install backend deps (GPU build of llama-cpp shown in `backend/requirements.txt`):
   `python -m pip install -r backend/requirements.txt`
2. Install frontend deps: `npm --prefix frontend install`
3. Put the model at `models/qwen2.5-3b-instruct.Q4_K_M.gguf`
   (or set `MODEL_PATH`).
4. `python start.py` → open http://localhost:5173

## Retrain the model

Open `training/train_colab.ipynb` in Colab (T4 GPU) and **Run all**. It fine-tunes
Qwen2.5-3B-Instruct with Unsloth (QLoRA 4-bit, 1 epoch, lr 5e-5), exports GGUF `q4_k_m`,
and saves it to `MyDrive/pocket_duelist/` in Google Drive. Copy that file into `models/`.

To rebuild the dataset from new game logs: play in “2P LOG” mode (logs go to
`backend/data/training_data.jsonl`), then run `clean_data.py` and `convert_to_sft.py` from `backend/`.
