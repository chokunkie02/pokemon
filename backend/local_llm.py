import os
import threading
from llama_cpp import Llama

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL_PATH = os.environ.get(
    "MODEL_PATH",
    os.path.join(_PROJECT_ROOT, "models", "qwen2.5-3b-instruct.Q4_K_M.gguf"),
)

# Singleton instance
_llm_instance = None
# llama.cpp is not thread-safe: two AI background tasks calling the model at once
# crash CUDA (access violation / GGML_ASSERT pool_used). Run one call at a time.
_llm_lock = threading.RLock()

def get_llm():
    with _llm_lock:
        return _load_llm()

def _load_llm():
    global _llm_instance
    if _llm_instance is None:
        print(f"[Local LLM] Loading local model from {MODEL_PATH} with n_gpu_layers=-1...")
        _llm_instance = Llama(
            model_path=MODEL_PATH,
            n_ctx=4096,
            n_batch=512,      # Reduced from 4096 for better VRAM stability on Windows
            flash_attn=False, # Disabled: caused GGML_ASSERT pool_used corruption on Windows CUDA
            n_gpu_layers=-1,  # Set to -1 to offload all layers to GPU for max speed
            verbose=False      # Skip excessive C++ logging
        )
        print("[Local LLM] Model loaded successfully!")
    return _llm_instance

def query_local_llm(system_prompt: str, user_prompt: str, max_tokens: int = 256) -> str:
    """
    Constructs a strict ChatML prompt and queries the local Qwen2.5 model.
    Returns the string text generated.
    max_tokens: Reduced default to 256 for faster responses (was 1024).
    """
    # Strict ChatML format required by Qwen2.5 instruct
    prompt = f"<|im_start|>system\n{system_prompt}<|im_end|>\n<|im_start|>user\n{user_prompt}<|im_end|>\n<|im_start|>assistant\n"

    with _llm_lock:
        llm = _load_llm()
        response = llm(
            prompt,
            max_tokens=max_tokens,
            temperature=0.1,
            stop=["<|im_end|>", "<|im_start|>"],
            echo=False
        )
    
    output_text = response['choices'][0]['text'].strip()
    return output_text
