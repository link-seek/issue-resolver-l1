#!/usr/bin/env python3
"""Query Zen /zen/v1/models, discover available free models, write litellm config."""
import json, os, sys, urllib.request

API_BASE = os.environ.get("DISCUSS_BASE", "https://opencode.ai/zen/v1")
KEYS = [os.environ.get(f"DISCUSS_KEY_{i}", "") for i in (1, 2, 3)]
KEYS = [k for k in KEYS if k]
PRIMARY_MODEL = os.environ.get("DISCUSS_MODEL", "mimo-v2.5-free")

# Known free-tier models (order = preference)
FREE_MODELS = [
    "mimo-v2.5-free",
    "nemotron-3.5-lightning-free",
    "ling-3.0-flash-fin-free",
    "big-pickle",
    "deepseek-v4-flash-free",
    "muse-spark-1.2-contributor-free",
    "nemotron-3-ultra-free",
    "laguna-s-2.1-free",
]


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
    with open("/tmp/litellm_config.yaml", "w") as f:
        # --- model_list ---
        f.write("model_list:\n")

        # Primary group: 3 keys for load balancing
        first_fb = f'"fb1"' if len(chain) > 1 else "[]"
        for key_var in ("DISCUSS_KEY_1", "DISCUSS_KEY_2", "DISCUSS_KEY_3"):
            f.write(f"""\
            - model_name: primary
              litellm_params:
                model: openai/{chain[0]}
                api_key: ${{{key_var}}}
                api_base: ${{DISCUSS_BASE}}
              fallbacks: [{first_fb}]\n""")

        # Fallback groups
        for i, fb_model in enumerate(chain[1:], 1):
            next_fb = f'"fb{i+1}"' if i + 1 < len(chain) else "[]"
            f.write(f"""\
            - model_name: fb{i}
              litellm_params:
                model: openai/{fb_model}
                api_key: ${{DISCUSS_KEY_1}}
                api_base: ${{DISCUSS_BASE}}
              fallbacks: [{next_fb}]\n""")

        # --- settings ---
        fb_groups = ",".join(f'"fb{i}"' for i in range(1, len(chain)))
        f.write(f"""\
          litellm_settings:
            cache: true
            cache_params:
              type: local
          router_settings:
            routing_strategy: least-busy
            num_retries: 3
            allowed_fails: 3
            request_timeout: 120
            fallbacks: [{{"primary": [{fb_groups}]}}]
          general_settings:
            master_key: sk-litellm-proxy
            drop_params: false
""")

    # Expand env vars (litellm can't do shell expansion)
    with open("/tmp/litellm_config.yaml") as f:
        config = f.read()
    for var in ("DISCUSS_KEY_1", "DISCUSS_KEY_2", "DISCUSS_KEY_3", "DISCUSS_BASE"):
        config = config.replace(f"${{{var}}}", os.environ.get(var, ""))
    with open("/tmp/litellm_config.yaml", "w") as f:
        f.write(config)


def health_check(model):
    """Quick probe: send 1-token request, return True if model responds."""
    body = json.dumps({
        "model": model, "max_tokens": 1,
        "messages": [{"role": "user", "content": "hi"}],
    }).encode()
    req = urllib.request.Request(
        f"{API_BASE}/chat/completions",
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
        tag = "ok" if ok else "skip"
        print(f"::debug::{m}: {tag}", file=sys.stderr)
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
