"""Serve gpt-oss-120b on Modal with vLLM, behind an API key, OpenAI-compatible.

    modal deploy oss/serve_gpt_oss.py     # prints the URL; endpoints live under <url>/v1
    modal app stop gpt-oss-serve          # stop paying for the GPU

The key comes from the Modal secret "oss-api-key" (env OSS_API_KEY). The same value is
stored in Valkyrie as "oss-api-key" so agents in the sandboxes can call it.
"""

import subprocess

import modal

MODEL = "openai/gpt-oss-120b"
PORT = 8000

image = (
    modal.Image.from_registry("nvidia/cuda:12.8.1-devel-ubuntu22.04", add_python="3.12")
    .entrypoint([])
    # transformers 5 breaks vllm 0.11's tokenizer loading, so pin the 4.x line it was built against
    .uv_pip_install("vllm==0.11.0", "transformers==4.57.1", "huggingface_hub")
    .env({"HF_XET_HIGH_PERFORMANCE": "1"})
)
weights = modal.Volume.from_name("gpt-oss-weights", create_if_missing=True)
vllm_cache = modal.Volume.from_name("vllm-cache", create_if_missing=True)

app = modal.App("gpt-oss-serve")


@app.function(
    image=image,
    gpu="H100",
    volumes={"/root/.cache/huggingface": weights, "/root/.cache/vllm": vllm_cache},
    secrets=[modal.Secret.from_name("oss-api-key")],
    timeout=60 * 60 * 4,
    scaledown_window=10 * 60,   # shut the GPU down after 10 idle minutes
)
@modal.concurrent(max_inputs=16)
@modal.web_server(port=PORT, startup_timeout=30 * 60)
def serve():
    import os
    # key goes in through VLLM_API_KEY, never on the command line (vllm logs its args)
    env = dict(os.environ, VLLM_API_KEY=os.environ["OSS_API_KEY"])
    subprocess.Popen([
        "vllm", "serve", MODEL,
        "--served-model-name", "gpt-oss-120b",
        "--host", "0.0.0.0", "--port", str(PORT),
        "--enable-auto-tool-choice", "--tool-call-parser", "openai",
        "--max-model-len", "131072",
        "--async-scheduling",
    ], env=env)
