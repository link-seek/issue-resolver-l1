#!/usr/bin/env python3
"""Discussion handler — @oh for analysis, @issue for structured issue creation."""

import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.request

from templates import get_template


def get_actual_model() -> str:
    """Extract actual model name from litellm Docker logs.

    Parses log lines like:
        litellm.acompletion(model=openai/mimo-v2.5-free) 200 OK
    Returns the actual model name (without openai/ prefix), or empty string.
    """
    try:
        result = subprocess.run(
            ["docker", "logs", "litellm"],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, timeout=30
        )
        output = result.stdout or ""
        # Match: litellm.acompletion(model=<actual_model>) <status>
        matches = re.findall(r'litellm\.acompletion\(model=([^)]+)\)', output)
        if matches:
            model = matches[-1].strip()
            # Strip openai/ prefix for display
            model = model.removeprefix("openai/")
            return model
    except Exception as e:
        print(f"[WARN] Failed to get actual model: {e}", file=sys.stderr)
    return ""


def gh_graphql(token: str, query: str, variables: dict = None) -> dict:
    url = "https://api.github.com/graphql"
    body = json.dumps({"query": query, "variables": variables or {}})
    req = urllib.request.Request(url, data=body.encode(), headers={
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json",
    }, method="POST")
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.load(resp)


def gh_rest(token: str, method: str, path: str, data: dict = None) -> dict:
    url = f"https://api.github.com{path}"
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, headers={
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json",
        "Content-Type": "application/json",
    }, method=method)
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.load(resp)


def get_discussion(token: str, node_id: str) -> dict:
    query = """
    query($id: ID!) {
      node(id: $id) {
        ... on Discussion {
          number
          title
          body
          category { name }
          comments(first: 50) {
            nodes {
              body
              author { login }
            }
          }
        }
      }
    }
    """
    result = gh_graphql(token, query, {"id": node_id})
    return result.get("data", {}).get("node", {})


def reply_discussion(token: str, discussion_node_id: str, body: str):
    query = """
    mutation($input: AddDiscussionCommentInput!) {
      addDiscussionComment(input: $input) {
        comment { id }
      }
    }
    """
    variables = {
        "input": {
            "discussionId": discussion_node_id,
            "body": body,
        }
    }
    return gh_graphql(token, query, variables)


def mark_discussion_answer(token: str, comment_node_id: str):
    query = """
    mutation($id: ID!) {
      markDiscussionCommentAsAnswer(input: {id: $id}) {
        discussion { id }
      }
    }
    """
    return gh_graphql(token, query, {"id": comment_node_id})


def close_discussion_resolved(token: str, discussion_node_id: str):
    query = """
    mutation($input: CloseDiscussionInput!) {
      closeDiscussion(input: $input) {
        discussion { id }
      }
    }
    """
    variables = {
        "input": {
            "discussionId": discussion_node_id,
            "reason": "RESOLVED"
        }
    }
    return gh_graphql(token, query, variables)


def create_issue(token: str, repo: str, title: str, body: str, labels: list) -> dict:
    return gh_rest(token, "POST", f"/repos/{repo}/issues", {
        "title": title,
        "body": body,
        "labels": labels,
    })


def get_file_tree(max_depth: int = 3) -> str:
    """Get a file tree of the current directory, excluding noise."""
    try:
        result = subprocess.run(
            ["find", ".", "-type", "f",
             "-not", "-path", "./.git/*",
             "-not", "-path", "./node_modules/*",
             "-not", "-path", "./target/*",
             "-not", "-path", "./__pycache__/*",
             "-not", "-path", "./.next/*",
             "-not", "-path", "./dist/*",
             "-not", "-name", "*.pyc",
             "-not", "-name", "*.log"],
            capture_output=True, text=True, timeout=10,
        )
        files = result.stdout.strip().split("\n") if result.stdout.strip() else []
        if len(files) > 200:
            files = files[:200]
        return "\n".join(files)
    except Exception:
        return "(无法获取文件树)"


def parse_issue_response(response: str) -> tuple:
    """Parse LLM response for to-issue mode.

    Returns (title, labels_list, body).
    """
    lines = response.strip().split("\n")
    title = ""
    labels = []
    body_start = 0

    for i, line in enumerate(lines):
        if line.startswith("ISSUE_TITLE:"):
            title = line[len("ISSUE_TITLE:"):].strip()
        elif line.startswith("ISSUE_LABELS:"):
            labels_str = line[len("ISSUE_LABELS:"):].strip()
            labels = [lbl.strip() for lbl in labels_str.split(",") if lbl.strip()]
            body_start = i + 1
            break

    body = "\n".join(lines[body_start:]).strip()
    if not title:
        title = lines[0].strip().lstrip("# ")
        body = "\n".join(lines[1:]).strip()
    if not body:
        body = response

    return title, labels, body


def run_llm(prompt: str, env: dict) -> str:
    """Run LLM agent and return response text."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        f.write(prompt)
        prompt_file = f.name

    agent_script = """import os, sys, io, re, json

# Capture stdout
captured = io.StringIO()
old_stdout = sys.stdout
sys.stdout = captured

import litellm

# Register proxy model alias so litellm's supports_function_calling() returns True.
# Without this, litellm.get_model_info() throws "This model isn't mapped yet" for
# the proxy model name (e.g. "openai/primary"), which causes
# supports_function_calling() to default to False, silently disabling all tool
# calls in the OpenHands SDK (see BerriAI/litellm#23054, OpenHands/OpenHands#8358).
# The agent then never calls FileEditor to write /tmp/llm_response.md.
_model_name = os.environ.get("LLM_MODEL", "")
_alias = _model_name.split("/")[-1] if "/" in _model_name else _model_name
if _alias and _alias not in litellm.model_cost:
    litellm.model_cost[_alias] = litellm.model_cost.get(_alias, {
        "supports_function_calling": True,
        "supports_tool_choice": True,
        "mode": "chat",
        "input_cost_per_token": 0,
        "output_cost_per_token": 0,
        "max_tokens": 128000,
    })
    litellm.model_cost[_model_name] = litellm.model_cost[_alias]

from openhands.sdk import LLM, Agent, AgentContext, Conversation
from openhands.sdk.tool import Tool
from openhands.tools.file_editor import FileEditorTool
from openhands.tools.terminal import TerminalTool
# Monkey-patch: skip MCP handler registration in BrowserUseServer.
# openhands-tools never serves MCP — it calls browser methods directly.
# The _setup_handlers() call uses @server.list_tools() which breaks with
# certain mcp SDK versions. See: https://github.com/OpenHands/software-agent-sdk/pull/4342
try:
    from openhands.tools.browser_use.server import CustomBrowserUseServer
    CustomBrowserUseServer._setup_handlers = lambda self: None
except ImportError:
    pass

from openhands.tools.browser_use import BrowserToolSet

llm = LLM(timeout=120,
    model=os.environ["LLM_MODEL"],
    base_url=os.environ["LLM_BASE_URL"],
    api_key=os.environ["LLM_API_KEY"],
    native_tool_calling=True,
    api_mode="responses",
)

# Force-enable tool calling for litellm proxy models.
# OpenHands SDK checks FUNCTION_CALLING_SUPPORTED_MODELS or litellm.supports_function_calling(),
# both return False for proxy model names like "openai/primary".
# See: BerriAI/litellm#23054, OpenHands/OpenHands#8358
llm._function_calling_active = True

tools = [
    Tool(name=TerminalTool.name),
    Tool(name=FileEditorTool.name),
    Tool(name=BrowserToolSet.name, params={"use_vision": False}),
]

# CodeGraph MCP: surgical code context
mcp_config = {
    "codegraph": {
        "command": "codegraph",
        "args": ["serve", "--mcp"],
    }
}

agent = Agent(llm=llm, tools=tools, mcp_config=mcp_config)
conversation = Conversation(agent=agent, max_iteration_per_run=50)

with open(os.environ["PROMPT_FILE"]) as f:
    prompt = f.read()

# Add instruction to write response to a file
prompt += "\\n\\n## 重要：输出要求\\n请严格按上方『回复模板』的结构将最终回复写入文件 /tmp/llm_response.md（markdown 格式）。这是你唯一的输出方式。\\n策略：一旦掌握回答所需的基本事实，立刻先写入包含『## 结论』的完整骨架，再用 FileEditor 逐节补充细化。绝不要把写文件留到最后一步——若工具调用轮次用尽而文件尚未创建，本次回复将作废。标题层级不可改动、章节不可省略，尖括号占位符必须替换为真实内容；禁止写入思考过程、工具调用结果、内部推理、Token 计数或 Agent Action 日志。不符合模板结构的回复会被系统拒绝。"

conversation.send_message(prompt)

# Debug: print state before run
sys.stdout = old_stdout
print(f"[DEBUG] execution_status before run: {conversation.state.execution_status}", file=sys.stderr)
print(f"[DEBUG] events count: {len(conversation.state.events)}", file=sys.stderr)
print(f"[DEBUG] _function_calling_active: {llm._function_calling_active}", file=sys.stderr)
sys.stdout = captured

conversation.run()

sys.stdout = old_stdout
raw = captured.getvalue()
print(f"[DEBUG] execution_status after run: {conversation.state.execution_status}", file=sys.stderr)
print(f"[DEBUG] events count after run: {len(conversation.state.events)}", file=sys.stderr)
for i, ev in enumerate(conversation.state.events):
    print(f"[DEBUG] event[{i}]: type={type(ev).__name__}, source={getattr(ev, 'source', 'N/A')}", file=sys.stderr)
    if hasattr(ev, 'llm_message') and ev.llm_message:
        content = getattr(ev.llm_message, 'content', None)
        if content:
            text = str(content)[:200] if not isinstance(content, list) else str([getattr(c, 'text', str(c))[:100] for c in content[:2]])
            print(f"[DEBUG]   content: {text}", file=sys.stderr)
    if hasattr(ev, 'detail'):
        print(f"[DEBUG]   detail: {getattr(ev, 'detail', 'N/A')}", file=sys.stderr)
print(f"[DEBUG] captured stdout length: {len(raw)}", file=sys.stderr)
if raw:
    print(f"[DEBUG] captured stdout (first 2000): {raw[:2000]}", file=sys.stderr)
    print(f"[DEBUG] captured stdout (last 2000): {raw[-2000:]}", file=sys.stderr)

# Read the response file written by the LLM
response = ""
try:
    with open("/tmp/llm_response.md") as f:
        response = f.read().strip()
except Exception as e:
    print(f"[WARN] Failed to read response file: {e}", file=sys.stderr)

required_marker = os.environ.get("REQUIRED_MARKER", "")

def is_valid_response(text):
    # Reject empty / tiny / off-template responses (e.g. raw tool dumps)
    if not text or len(text.strip()) < 30:
        return False
    if required_marker and required_marker not in text:
        return False
    return True

# Clean agent internal output patterns from response
def clean_response(text):
    if not text:
        return text
    lines = text.split('\\n')
    cleaned = []
    skip_block = False
    for line in lines:
        stripped = line.strip()
        # Skip agent internal output markers
        if any(stripped.startswith(m) for m in [
            'Agent Action', 'Observation', 'Tokens:', 'Tool:', 'Result:',
            'Thought:', 'Thinking:', 'Summary:', '🤔 Thinking:',
            'Finish with message:', '📁 Working directory:',
            '🐍 Python interpreter:', '✅ Exit code:',
        ]):
            skip_block = True
            continue
        if skip_block:
            # End skip block on next markdown heading or blank line after content
            if stripped.startswith('#') and not stripped.startswith('#!'):
                skip_block = False
                cleaned.append(line)
            continue
        # Skip lines that look like file paths from tool output
        if stripped.startswith('/home/runner/') or stripped.startswith('/opt/'):
            continue
        cleaned.append(line)
    return '\\n'.join(cleaned).strip()

response = clean_response(response)
if not is_valid_response(response):
    response = ""

# Fallback: try conversation.state
if not response:
    try:
        state = conversation.state
        for attr in ['messages', 'history', 'events', '_messages', '_history']:
            val = getattr(state, attr, None)
            if val and isinstance(val, (list, tuple)) and len(val) > 0:
                last = val[-1]
                for msg_attr in ['content', 'text', 'message', 'response', 'output', 'data', 'body']:
                    cand = getattr(last, msg_attr, None)
                    if cand and isinstance(cand, str):
                        cand = clean_response(cand)
                        if is_valid_response(cand):
                            response = cand
                            break
                if response:
                    break
    except:
        pass

# Fallback: parse stdout - find content after last tool output, before Tokens:
if not response:
    lines = raw.split('\\n')
    end_idx = len(lines)
    for i, line in enumerate(lines):
        if 'Tokens:' in line or 'Finish with message:' in line:
            end_idx = i
            break
    # Find start: look for the last line that looks like a markdown heading
    # after the middle of the output (to skip system prompt and user message)
    start_idx = end_idx
    mid = len(lines) // 2
    for i in range(end_idx - 1, mid, -1):
        line = lines[i].strip()
        if line.startswith('#') and not line.startswith('#!'):
            start_idx = i
            break
    if start_idx < end_idx:
        resp_cand = '\\n'.join(lines[start_idx:end_idx]).strip()
        if is_valid_response(clean_response(resp_cand)):
            response = resp_cand

# Final guard: never publish unvalidated raw output
if not response:
    response = "(Agent 未能生成规范回复，请重试)"

# Truncate
if len(response) > 65000:
    response = response[:65000] + "\\n\\n...(内容过长已截断)"

with open(os.environ["RESPONSE_FILE"], 'w') as f:
    f.write(response)

# Force exit to kill Chrome and prevent subprocess hang
os._exit(0)
"""

    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write(agent_script)
        script_file = f.name

    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        response_file = f.name

    try:
        subprocess.run(
            ["uv", "run", "--no-project",
             "--with", "openhands-sdk",
             "--with", "openhands-tools",
             "python", script_file],
            stdout=subprocess.PIPE, stderr=None, text=True, timeout=1800,
            env={**env, "PROMPT_FILE": prompt_file,
                 "RESPONSE_FILE": response_file},
            cwd=os.getcwd(),
        )
    except subprocess.TimeoutExpired:
        print("[ERROR] Agent timed out after 1800s", file=sys.stderr)
        return "(Agent 执行超时，请稍后重试)"

    try:
        with open(response_file) as f:
            return f.read().strip()
    except Exception:
        return "(LLM 未返回文本回复)"


def main():
    token = os.environ.get("GITHUB_TOKEN", "")
    discussion_node_id = os.environ.get("DISCUSSION_NODE_ID", "")
    repo_name = os.environ.get("REPO_NAME", "")
    discuss_mode = os.environ.get("DISCUSS_MODE", "discuss")
    llm_model = os.environ.get("LLM_MODEL", "openai/primary")
    llm_base_url = os.environ.get("LLM_BASE_URL", "")
    llm_api_key = os.environ.get("LLM_API_KEY", "")
    _ = (llm_model, llm_base_url, llm_api_key)  # used via env in subprocess

    model_display_map = {
        "openai/primary": "GLM",
        "openai/secondary": "DeepSeek-V4-Flash",
    }
    model_display_name = os.environ.get("LLM_MODEL_DISPLAY") or model_display_map.get(llm_model, llm_model)

    if not discussion_node_id:
        print("No DISCUSSION_NODE_ID set")
        sys.exit(1)

    discussion = get_discussion(token, discussion_node_id)
    title = discussion.get("title", "")
    body = discussion.get("body", "")
    category = discussion.get("category", {}).get("name", "")
    discussion_number = discussion.get("number", "")
    comments = discussion.get("comments", {}).get("nodes", [])

    print(f"Discussion: {title}")
    print(f"Category: {category}")
    print(f"Comments: {len(comments)}")
    print(f"Mode: {discuss_mode}")

    comment_history = "\n\n".join([
        f"**{c['author']['login']}**: {c['body']}" for c in comments
    ])

    file_tree = get_file_tree()
    print(f"File tree: {len(file_tree.split(chr(10)))} files")

    llm_env = {**os.environ}
    llm_env["REQUIRED_MARKER"] = "ISSUE_TITLE:" if discuss_mode == "to-issue" else "## 结论"

    if discuss_mode == "to-issue":
        prompt = get_template(
            "prompt_discuss_to_issue",
            repo_name=repo_name, file_tree=file_tree, title=title,
            category=category, body=body, comment_history=comment_history,
            discussion_number=discussion_number,
        )
    else:
        admin_email = os.environ.get("EAP_ADMIN_EMAIL", "")
        admin_password = os.environ.get("EAP_ADMIN_PASSWORD", "")
        # Python-side deterministic first-reply detection (bot has no replies yet)
        bot_login = os.environ.get("BOT_LOGIN", "link-seek-bot")
        is_first_reply = not any(
            (c.get("author") or {}).get("login") == bot_login for c in comments
        )
        print(f"First reply: {is_first_reply}")

        response_template = get_template(
            "response_first_reply" if is_first_reply else "response_followup"
        )
        prompt = get_template(
            "prompt_discuss",
            repo_name=repo_name, file_tree=file_tree, title=title,
            category=category, body=body, comment_history=comment_history,
            admin_email=admin_email, admin_password=admin_password,
            response_template=response_template,
        )

    print("Sending to LLM...")
    llm_response = run_llm(prompt, llm_env)
    print(f"Response length: {len(llm_response)} chars")

    # Try to detect actual model from litellm logs (overrides configured model name)
    actual_model = get_actual_model()
    if actual_model:
        model_display_name = actual_model
        print(f"Actual model used: {model_display_name}")

    if discuss_mode == "to-issue":
        issue_title, issue_labels, issue_body = parse_issue_response(llm_response)

        if "fix-me" not in issue_labels:
            issue_labels.append("fix-me")

        print(f"Creating issue: {issue_title}")
        print(f"Labels: {issue_labels}")

        try:
            issue = create_issue(token, repo_name, issue_title, issue_body, issue_labels)
            issue_number = issue["number"]
            issue_url = issue["html_url"]
            print(f"Issue created: #{issue_number} {issue_url}")

            reply_body = get_template(
                "issue_created_reply",
                issue_number=issue_number,
                issue_title=issue_title,
                issue_url=issue_url,
                issue_labels=", ".join(issue_labels),
            )

            try:
                result_gql = reply_discussion(token, discussion_node_id, reply_body)
                comment_id = result_gql.get("data", {}).get("addDiscussionComment", {}).get("comment", {}).get("id")
                if comment_id:
                    try:
                        mark_discussion_answer(token, comment_id)
                        print("Discussion marked as answered")
                    except Exception as e:
                        print(f"Failed to mark discussion as answered: {e}")
                print("Reply posted to discussion")
            except Exception as e:
                print(f"Failed to post reply: {e}")

            try:
                close_discussion_resolved(token, discussion_node_id)
                print("Discussion closed as RESOLVED")
            except Exception as e:
                print(f"Failed to close discussion: {e}")
        except Exception as e:
            print(f"Failed to create issue: {e}")
            error_reply = f"## Issue 创建失败\n\n错误: {e}\n\n---\n🤖 由 AI Agent 生成"
            try:
                reply_discussion(token, discussion_node_id, error_reply)
            except Exception as e:
                print(f"Failed to reply discussion error: {e}")
    else:
        reply_body = get_template("discussion_reply", llm_response=llm_response, model_name=model_display_name)

        try:
            result_gql = reply_discussion(token, discussion_node_id, reply_body)
            if "errors" in result_gql:
                print(f"GraphQL errors: {result_gql['errors']}")
            else:
                print("Reply posted to discussion")
        except Exception as e:
            print(f"Failed to post reply: {e}")


if __name__ == "__main__":
    main()
