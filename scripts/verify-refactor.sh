#!/usr/bin/env bash
set -euo pipefail
CONSUMER="link-seek/enterprise-architecture-platform"
L1="link-seek/issue-resolver-l1"
PASS=0; FAIL=0

check() { local desc=$1; local result=$2; local expect=$3
  if [ "$result" = "$expect" ]; then
    echo "✅ $desc"; PASS=$((PASS+1))
  else
    echo "❌ $desc (got: $result, expect: $expect)"; FAIL=$((FAIL+1))
  fi
}

fetch() { gh api "repos/$1/contents/$2" --jq '.content' | base64 -d; }
list_wf() { gh api "repos/$1/contents/.github/workflows" --jq '.[].name'; }
ge() { [ "$1" -ge "$2" ] && echo 1 || echo 0; }

echo "=== Phase 1: 层违规消除 ==="
CNT=$(fetch "$L1" ".github/workflows/pr-review.yml" | grep -c "gh workflow run" || true)
check "pr-review.yml 无 gh workflow run" "$CNT" "0"
CNT=$(fetch "$L1" ".github/workflows/pr-review.yml" | grep -c "auto-fix-workflow" || true)
check "pr-review.yml 无 auto-fix-workflow" "$CNT" "0"
CNT=$(fetch "$L1" ".github/workflows/pr-review.yml" | grep -c "continue-fix" || true)
check "pr-review.yml 无 continue-fix" "$CNT" "0"
CNT=$(fetch "$L1" ".github/workflows/pr-review.yml" | grep -c "@agent" || true)
check "pr-review.yml 有 @agent 评论" "$(ge $CNT 1)" "1"
CNT=$(fetch "$CONSUMER" ".github/workflows/on-pr-review.yml" | grep -c "issue_comment" || true)
check "on-pr-review.yml 无 issue_comment" "$CNT" "0"

echo ""
echo "=== Phase 2: 触发工作流合并 ==="
check "on-fix.yml 存在" "$(list_wf "$CONSUMER" | grep -c "^on-fix.yml$")" "1"
CNT=$(fetch "$CONSUMER" ".github/workflows/on-fix.yml" | grep -c "issue_comment" || true)
check "on-fix.yml 有 issue_comment" "$(ge $CNT 1)" "1"
CNT=$(fetch "$CONSUMER" ".github/workflows/on-fix.yml" | grep -c "labeled" || true)
check "on-fix.yml 有 labeled 触发" "$(ge $CNT 1)" "1"
CNT=$(fetch "$CONSUMER" ".github/workflows/on-fix.yml" | grep -c "fix.yml@main" || true)
check "on-fix.yml 调用 fix.yml" "$(ge $CNT 1)" "1"
CNT=$(fetch "$CONSUMER" ".github/workflows/on-deploy.yml" | grep -c "deploy-broken" || true)
check "on-deploy.yml 有 deploy-broken" "$(ge $CNT 1)" "1"
for f in on-quick-fix.yml on-comment-fix.yml on-label.yml; do
  check "$f 已删除" "$(list_wf "$CONSUMER" | grep -c "^$f$")" "0"
done

echo ""
echo "=== Phase 2.5: Quick-fix 在 L1 ==="
CNT=$(fetch "$L1" ".github/workflows/fix.yml" | grep -c "opencode" || true)
check "fix.yml 有 opencode quick-fix" "$(ge $CNT 1)" "1"
CNT=$(fetch "$L1" ".github/workflows/fix.yml" | grep -c "quick-fix-fail" || true)
check "fix.yml 有失败计数" "$(ge $CNT 1)" "1"
CNT=$(fetch "$L1" ".github/workflows/fix.yml" | grep -c "deepseek" || true)
check "fix.yml 用 deepseek 模型" "$(ge $CNT 1)" "1"

echo ""
echo "=== Phase 3: 月度清理解耦 ==="
CNT=$(fetch "$L1" ".github/workflows/monthly-cleanup.yml" | grep -c "fix-me" || true)
check "monthly-cleanup.yml 无 fix-me 标签" "$CNT" "0"
CNT=$(fetch "$L1" ".github/workflows/monthly-cleanup.yml" | grep -c "fix.yml@main" || true)
check "monthly-cleanup.yml 直接调 fix.yml" "$(ge $CNT 1)" "1"

echo ""
echo "=== Phase 4: 重命名 ==="
check "on-push.yml 存在" "$(list_wf "$CONSUMER" | grep -c "^on-push.yml$")" "1"
check "on-pr.yml 存在" "$(list_wf "$CONSUMER" | grep -c "^on-pr.yml$")" "1"
check "on-push-build.yml 已删除" "$(list_wf "$CONSUMER" | grep -c "^on-push-build.yml$")" "0"
check "on-pr-check.yml 已删除" "$(list_wf "$CONSUMER" | grep -c "^on-pr-check.yml$")" "0"

echo ""
echo "=== 架构不变量 ==="
for f in $(list_wf "$CONSUMER"); do
  CNT=$(fetch "$CONSUMER" ".github/workflows/$f" | grep -c "gh workflow run" || true)
  check "消费仓 $f 无 gh workflow run" "$CNT" "0"
done
for f in $(list_wf "$L1"); do
  CNT=$(fetch "$L1" ".github/workflows/$f" | grep -c "gh workflow run" || true)
  check "L1 $f 无 gh workflow run" "$CNT" "0"
done
CNT=$(list_wf "$CONSUMER" | wc -l)
check "消费仓工作流数 ≤ 8" "$(ge 8 $CNT)" "1"

echo ""
echo "=============================="
echo "结果: ✅ $PASS 通过, ❌ $FAIL 失败"
echo "=============================="
[ $FAIL -eq 0 ] && exit 0 || exit 1
