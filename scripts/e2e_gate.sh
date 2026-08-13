#!/usr/bin/env bash
# e2e-gate: E2E 准入门禁
#
# 检查项：
#   1. 标签完整性 — 所有 .spec.ts 中的 test() 必须有 @smoke 或 @regression 标签
#   2. 测试文件存在性 — 改了源码 → 对应测试目录有 .spec.ts 文件
#
# 用法：
#   ./e2e_gate.sh [repo-root]
#
# 退出码：
#   0 — 通过
#   1 — 有违规项（详情输出到 stdout）

set -euo pipefail

ROOT="${1:-.}"
TESTS_DIR="$ROOT/frontend/tests"
FAILURES=()

# ── 检查 1: 标签完整性 ──────────────────────────────────────────
check_tags() {
  local spec_files
  spec_files=$(find "$TESTS_DIR" -name '*.spec.ts' 2>/dev/null) || return 0

  while IFS= read -r file; do
    [ -z "$file" ] && continue
    local rel="${file#$ROOT/}"

    # 找所有 test( 或 test.skip( 或 test.only( 行
    while IFS= read -r line_num; do
      [ -z "$line_num" ] && continue
      local line_content
      line_content=$(sed -n "${line_num}p" "$file")

      # 跳过 test.describe / test.beforeEach / test.afterEach 等非 test 调用
      if echo "$line_content" | grep -qE 'test\.(describe|beforeEach|afterEach|beforeAll|afterAll|step)\s*\('; then
        continue
      fi

      # 检查是否有 @smoke 或 @regression
      if ! echo "$line_content" | grep -qE '@(smoke|regression)'; then
        local test_name
        test_name=$(echo "$line_content" | grep -oE "test[^(]*\(\s*['\"][^'\"]*['\"]" | head -1 | sed "s/.*['\"]//;s/['\"]$//")
        FAILURES+=("TAG_MISSING|$rel:$line_num|${test_name:-unnamed}")
      fi
    done < <(grep -nE 'test[^.]*\(' "$file" | grep -vE 'test\.(describe|beforeEach|afterEach|beforeAll|afterAll|step)' | cut -d: -f1)
  done <<< "$spec_files"
}

# ── 检查 2: 测试文件存在性 ──────────────────────────────────────
check_test_existence() {
  [ ! -d "$ROOT/.git" ] && return 0

  local changed_files
  changed_files=$(cd "$ROOT" && git diff --name-only HEAD~1 HEAD 2>/dev/null) || return 0

  while IFS= read -r src_file; do
    [ -z "$src_file" ] && continue

    # 只检查 frontend/src 下的源文件
    echo "$src_file" | grep -qE '^frontend/src/' || continue
    # 跳过非组件/页面文件（utils, types, constants 等不需要 E2E）
    echo "$src_file" | grep -qE '\.(tsx|ts)$' || continue
    echo "$src_file" | grep -qE '(utils|types|constants|hooks|api|store|lib|config)' && continue

    # 从源文件路径推导测试路径
    # frontend/src/components/Foo.tsx → frontend/tests/components/foo.spec.ts
    local basename
    basename=$(echo "$src_file" | xargs basename | sed 's/\.\(tsx\|ts\)$//')
    local kebab_name
    kebab_name=$(echo "$basename" | sed -E 's/([a-z0-9])([A-Z])/\1-\2/g' | tr '[:upper:]' '[:lower:]')
    local dir
    dir=$(echo "$src_file" | sed 's|^frontend/src/||; s|/[^/]*$||')

    # 检查几种可能的测试路径
    local found=0
    for test_path in \
      "$TESTS_DIR/${dir}/${kebab_name}.spec.ts" \
      "$TESTS_DIR/${dir}/${basename,,}.spec.ts" \
      "$TESTS_DIR/${kebab_name}.spec.ts"; do
      [ -f "$test_path" ] && found=1 && break
    done

    # 也检查是否有任何 .spec.ts 在对应目录
    if [ "$found" -eq 0 ]; then
      local dir_tests
      dir_tests=$(find "$TESTS_DIR/${dir}" -name '*.spec.ts' 2>/dev/null | head -1)
      [ -n "$dir_tests" ] && found=1
    fi

    if [ "$found" -eq 0 ]; then
      FAILURES+=("TEST_MISSING|$src_file|no .spec.ts found in tests/${dir}/")
    fi
  done <<< "$changed_files"
}

# ── 主逻辑 ──────────────────────────────────────────────────────
echo "=== E2E Gate ==="
echo "Checking: $ROOT"
echo ""

check_tags
check_test_existence

# ── 输出结果 ──────────────────────────────────────────────────────
TAG_ISSUES=0
TEST_ISSUES=0

for f in "${FAILURES[@]}"; do
  type="${f%%|*}"
  case "$type" in
    TAG_MISSING)  ((TAG_ISSUES++)) ;;
    TEST_MISSING) ((TEST_ISSUES++)) ;;
  esac
done

if [ ${#FAILURES[@]} -eq 0 ]; then
  echo "✅ E2E gate passed"
  exit 0
fi

echo "❌ E2E gate failed"
echo ""

if [ "$TAG_ISSUES" -gt 0 ]; then
  echo "## 标签缺失 ($TAG_ISSUES)"
  echo "以下 test() 缺少 @smoke 或 @regression 标签："
  echo ""
  for f in "${FAILURES[@]}"; do
    type="${f%%|*}"
    [ "$type" != "TAG_MISSING" ] && continue
    rest="${f#*|}"
    echo "  - $rest"
  done
  echo ""
fi

if [ "$TEST_ISSUES" -gt 0 ]; then
  echo "## 测试缺失 ($TEST_ISSUES)"
  echo "以下源文件缺少对应 E2E 测试："
  echo ""
  for f in "${FAILURES[@]}"; do
    type="${f%%|*}"
    [ "$type" != "TEST_MISSING" ] && continue
    rest="${f#*|}"
    echo "  - $rest"
  done
  echo ""
fi

exit 1
