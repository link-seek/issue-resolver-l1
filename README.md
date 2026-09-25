# OpenHands Issue Resolver Plugin

Automatically resolve GitHub issues by creating PRs with fixes using OpenHands agents.

## Features

- Reads issue content from GitHub
- Uses OpenHands agent (DeepSeek-V4-Flash) to explore codebase and implement fix
- Runs tests to verify changes
- Creates a pull request automatically
- Comments on issue with progress and result

## Usage

### In a workflow:

```yaml
name: Auto-resolve issues

on:
  issues:
    types: [labeled]

jobs:
  resolve:
    if: github.event.label.name == 'fix-me' || github.event.label.name == 'build-feature'
    runs-on: ubuntu-latest
    steps:
      - uses: link-seek/issue-resolver@main
        with:
          llm-model: openai/muse-spark-1.3-contributor
          llm-base-url: https://opencode.ai/zen/go/v1
          llm-api-key: ${{ secrets.DISCUSS_API_KEY_1 }}
          github-token: ${{ secrets.PAT_TOKEN }}
          issue-number: ${{ github.event.issue.number }}
          issue-type: issue
```

### Labels

- `fix-me` — Bug fixes
- `build-feature` — New features

Both work the same way — the agent reads the issue and implements whatever is described.

## 版本政策（Versioning Policy）

- **Workflow 文件按 tag pin**：调用仓 `uses: link-seek/issue-resolver-l1/.github/workflows/fix.yml@<tag>`，流程步骤随 tag 锁定。
- **Scripts 随 `main` 持续交付**：`fix.yml` / `discuss.yml` / `pr-ci.yml` 内"Checkout issue-resolver scripts"固定 `ref: main`，
  脚本修复合进 main 即全网生效，无需发版。这是刻意设计（pilot Task6 Step2 的 poll 直合修复即靠此零发版惠及旧 pin 仓）。
- **含义**：旧 pin ≠ 旧行为；回退 pin 不能回退脚本行为。应急回滚脚本请 revert 脚本提交本身。
- **可追溯**：每次 run 在"Log L1 scripts version"步骤打印 `L1 scripts SHA=<commit>`（日志 + Step Summary），出事按 SHA 定位。
