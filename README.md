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
          llm-model: openai/deepseek-v4-flash
          llm-base-url: https://api.deepseek.com
          llm-api-key: ${{ secrets.LLM_API_KEY }}
          github-token: ${{ secrets.PAT_TOKEN }}
          issue-number: ${{ github.event.issue.number }}
          issue-type: issue
```

### Labels

- `fix-me` — Bug fixes
- `build-feature` — New features

Both work the same way — the agent reads the issue and implements whatever is described.
