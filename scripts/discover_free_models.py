#!/usr/bin/env python3
"""Query Zen /zen/v1/models, discover available free models, write litellm config."""
import json, os, sys, urllib.request
from pathlib import Path

API_BASE = os.environ.get("DISCUSS_BASE", "https://opencode.ai/zen/v1")
KEYS = [os.environ.get(f"DISCUSS_KEY_{i}", "") for i in (1, 2, 3)]
KEYS = [k for k in KEYS if k]
PRIMARY_MODEL = os.environ.get("DISCUSS_MODEL", "muse-spark-1.2-contributor-free")

# Known free-tier models (order = preference)
FREE_MODELS = [
    "muse-spark-1.2-contributor-free",
    "mimo-v2.5-free",
    "nemotron-3.5-lightning-free",
    "ling-3.0-flash-fin-free",
    "deepseek-v4-flash-free",
    "nemotron-3-ultra-free",
    "laguna-s-2.1-free",
]

# Load model endpoint configuration
ENDPOINTS_CONFIG_PATH = Path(__file__).parent / "model_endpoints.json"


def load_endpoints_config():
    """Load model endpoint configuration from JSON file."""
    try:
        with open(ENDPOINTS_CONFIG_PATH) as f:
            config = json.load(f)
            return config.get("models", {})
    except Exception as e:
        print(f"::warning::failed to load endpoints config: {e}", file=sys.stderr)
        return {}


def get_model_endpoint(model_id):
    """Get the endpoint type for a model. Returns 'chat_completions' or 'responses'."""
    config = load_endpoints_config()
    model_config = config.get(model_id, {})
    return model_config.get("endpoint", "chat_completions")


def get_litellm_prefix(model_id):
    """Get the LiteLLM model prefix based on endpoint type.
    
    - 'chat_completions' -> 'openai/{model}' (default)
    - 'responses' -> 'openai/responses/{model}' (forces Responses API)
    """
    endpoint = get_model_endpoint(model_id)
    if endpoint == "responses":
        return f"openai/responses/{model_id}"
    return f"openai/{model_id}"


def fetch_available():
    """GET /models, return set of model ids."""
    req = urllib.request.Request(
        f"{API_BASE}/models",
        headers={
            "Authorization": f"Bearer {KEYS[0]}",
            "User-Agent": "OpenCode-Discuss/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.load(resp)
            return {m["id"] for m in data.get("data", [])}
    except Exception as e:
        print(f"::warning::model discovery failed: {e}", file=sys.stderr)
        return set()


def build_config(chain):
    """Build litellm YAML config. chain = [primary, fb1, fb2, ...]."""
    lines = []
    lines.append("model_list:")

    # Primary group: 3 keys for load balancing
    first_fb = '"fb1"' if len(chain) > 1 else "[]"
    for key_var in ("DISCUSS_KEY_1", "DISCUSS_KEY_2", "DISCUSS_KEY_3"):
        lines.append(f"  - model_name: primary")
        lines.append(f"    litellm_params:")
        lines.append(f"      model: {get_litellm_prefix(chain[0])}")
        lines.append(f"      api_key: ${{{key_var}}}")
        lines.append(f"      api_base: ${{DISCUSS_BASE}}")
        lines.append(f"    fallbacks: [{first_fb}]")

    # Fallback groups
    for i, fb_model in enumerate(chain[1:], 1):
        next_fb = f'"fb{i+1}"' if i + 1 < len(chain) else "[]"
        lines.append(f"  - model_name: fb{i}")
        lines.append(f"    litellm_params:")
        lines.append(f"      model: {get_litellm_prefix(fb_model)}")
        lines.append(f"      api_key: ${{DISCUSS_KEY_1}}")
        lines.append(f"      api_base: ${{DISCUSS_BASE}}")
        lines.append(f"    fallbacks: [{next_fb}]")

    # Settings
    fb_groups = ",".join(f'"fb{i}"' for i in range(1, len(chain)))
    lines.append("litellm_settings:")
    lines.append("  verbose: true")
    lines.append("  cache: true")
    lines.append("  cache_params:")
    lines.append("    type: local")
    lines.append("router_settings:")
    lines.append("  routing_strategy: least-busy")
    lines.append("  num_retries: 3")
    lines.append("  allowed_fails: 3")
    lines.append("  request_timeout: 120")
    lines.append(f'  fallbacks: [{{"primary": [{fb_groups}]}}]')
    lines.append("general_settings:")
    lines.append("  master_key: sk-litellm-proxy")
    lines.append("  drop_params: false")

    with open("/tmp/litellm_config.yaml", "w") as f:
        f.write("\n".join(lines) + "\n")

    # Expand env vars (litellm can't do shell expansion)
    with open("/tmp/litellm_config.yaml") as f:
        config = f.read()
    for var in ("DISCUSS_KEY_1", "DISCUSS_KEY_2", "DISCUSS_KEY_3", "DISCUSS_BASE"):
        config = config.replace(f"${{{var}}}", os.environ.get(var, ""))
    with open("/tmp/litellm_config.yaml", "w") as f:
        f.write(config)


def health_check(model):
    """Quick probe: send 1-token request, return True if model responds.
    
    Uses the appropriate endpoint based on model_endpoints.json config:
    - 'chat_completions' -> POST /chat/completions
    - 'responses' -> POST /responses
    """
    endpoint = get_model_endpoint(model)
    
    if endpoint == "responses":
        # Use Responses API endpoint
        body = json.dumps({
            "model": model,
            "input": "hi",
            "stream": False,
        }).encode()
        url = f"{API_BASE}/responses"
    else:
        # Use Chat Completions endpoint (default)
        body = json.dumps({
            "model": model,
            "max_tokens": 1,
            "messages": [{"role": "user", "content": "hi"}],
        }).encode()
        url = f"{API_BASE}/chat/completions"
    
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Authorization": f"Bearer {KEYS[0]}",
            "Content-Type": "application/json",
            "User-Agent": "OpenCode-Discuss/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            return resp.status == 200
    except Exception:
        return False


def main():
    available = fetch_available()
    candidates = [m for m in FREE_MODELS if m in available]

    # Quick health check: skip models that don't respond
    healthy = []
    for m in candidates:
        ok = health_check(m)
        endpoint = get_model_endpoint(m)
        tag = "ok" if ok else "skip"
        print(f"::debug::{m}: {tag} (endpoint={endpoint})", file=sys.stderr)
        if ok:
            healthy.append(m)

    # Always put primary first
    if PRIMARY_MODEL in healthy:
        healthy.remove(PRIMARY_MODEL)
    chain = [PRIMARY_MODEL] + healthy

    if len(chain) < 2:
        chain = [PRIMARY_MODEL, "nemotron-3.5-lightning-free", "ling-3.0-flash-fin-free"]
        print("::warning::health check found <2 healthy models, using hardcoded fallback",
              file=sys.stderr)

    print(f"::notice::fallback chain: {' → '.join(chain)}", file=sys.stderr)
    build_config(chain)
    print("active_model=openai/primary")


if __name__ == "__main__":
    main()
