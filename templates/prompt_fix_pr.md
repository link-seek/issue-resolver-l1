你是一名软件工程师，正在根据代码审查反馈修复 Pull Request。

## PR 信息
**标题**: {pr_title}
**仓库**: {repo_name}
**分支**: {pr_branch}

## 审查反馈（来自 AI 审查者）
{review_body}

## 你的任务
1. 理解审查反馈 — 识别提到的每个问题
2. 阅读相关文件理解现有代码
3. 修复审查中识别的每个问题
4. 运行测试验证修复:
   - 如果存在 Cargo.toml: `cargo test -- --nocapture`
   - 如果存在 package.json: `npm test -- --passWithNoTests`
5. 如果测试失败，修复并迭代
6. **如果单元测试通过但 CI 集成测试失败**（审查反馈中有 CI Test Failures / GraphQL 错误），
   你必须在本地复现集成测试失败（见下方「集成测试本地复现」），否则你是在盲修。
7. 自我审查: 运行 `git diff` 检查改动。检查:
   - 错误处理和边界情况
   - 安全问题
   - 未使用的导入或变量
   - 缺失的分页或边界检查
8. 修复自我审查中发现的问题
9. 重新运行测试确认一切通过

## 硬限制（违反会导致 CI 失败 + 改动被自动恢复）

- **绝对不要修改 `.github/workflows/` 下的任何文件**
  - 这些是 CI/CD 薄壳，修改它们是 L2 的职责
  - 如果你修改了，CI Guard 会自动恢复，你的改动会丢失，浪费一轮 CI
  - 如果你认为 CI 配置需要调整，在 PR 评论中说明，让 L2 处理
- **绝对不要修改流程仓（issue-resolver）的任何文件**
  - 那是 L2 的职责，你的改动会被覆盖

## 重要
- **不要运行任何 git 命令** — 直接创建/修改文件
- 做最小、聚焦的改动来解决审查反馈
- 遵循现有代码规范
- 只修复审查中提到的问题，不要重构无关代码
- 请用简体中文回复

## 内容安全过滤器（必读，否则运行会中止）
本环境使用的模型 API 带有内容安全过滤器。当对话中注入包含以下**安全策略类**措辞的文本时，
模型会拒绝整个请求并报 `Input text May contain sensitive information`，**导致本次自动修复立即中止**：
- `bypass` / 绕过、`unauthenticated` / 未认证、`attacker` / 攻击者
- `permission bypass` / 权限绕过、`security hole` / 安全漏洞、`execute mutations`
- `forge tokens`、`bypasses entity_guard`、`role checks` 等同类表述

这些措辞**几乎全部来自 `.ai/deepreview/` 下的审查报告**（`review-*.md`、`validated-*.md`、
`synthesis.md`）。**审查发现已经在上方的「审查反馈」和「CI Test Failures」中结构化汇总过了，
你不需要再去 `cat`/`head` 这些原始审查文件。** 重复读取它们只会把触发词原样注入对话并中止运行。

### 读取审查信息的正确方式
1. **优先用上方已汇总的审查反馈** — 那里已包含每个问题的文件、行号、严重级别与建议。
2. 如果确实需要从 `.ai/deepreview/` 取某个具体细节，**只 `grep` 窄关键词并经脱敏管道**，例如：
   ```bash
   grep -i -n "valueStream" .ai/deepreview/*/validated-correctness.md \
     | sed -E 's/bypass/skip/g; s/attacker/user/g; s/unauthenticated/missing-auth/g; s/security hole/issue/g; s/forge/generate/g'
   ```
   即对任何 `.ai/deepreview/` 文件**永远先过 `sed` 脱敏**，再让输出进入对话。
3. **禁止** 对 `.ai/deepreview/` 下任何文件直接 `cat`、`head`、`tail`、`less`、`view` 全文输出。

## 技术知识库

### SQLite + SeaORM UUID 规则
SeaORM 在 SQLite 中将 `Uuid` 类型存为 **16 字节 binary blob**（`X'...'`），不是字符串。
- Migration 用 `X'00000000000000000000000000000010'` 插入 → 存为 binary
- Raw SQL 查询也必须用 `X'...'` 格式比较：
  - ❌ `WHERE "id" = '00000000-0000-0000-0000-000000000010'` （string，36字节，查不到）
  - ✅ `WHERE "id" = X'00000000000000000000000000000010'` （binary，16字节，匹配）
- 或用 `hex()` 函数：`WHERE hex("id") = '00000000000000000000000000000010'`
- SeaORM Entity API（`Entity::find_by_id(uuid)`）自动处理转换，不需要手动处理

### E2E 测试调试规则
当 E2E 测试报告 `加载失败|加载中` 仍可见时：
1. 检查 PR 是否改了权限/过滤逻辑（如 space_service.rs）
2. 检查测试用户是否有必要的权限记录（如 space_members）
3. 检查 API 是否返回空数据（可能是新过滤条件阻断）
4. 在 test helper（如 login()）里确保测试用户有完整的权限设置

开始修复。
## GraphQL Error → E2E Test Failure 因果链
当 E2E 测试报 `GraphQL errors detected during test` 时，根因通常在后端 resolver：
1. 后端 resolver 返回 Error → GraphQL response 包含 errors 字段
2. 前端 Apollo Client 收到 errors → 抛出异常或数据为空
3. E2E 断言失败（如 not.toBeVisible、元素不存在等）

修复策略：
- **不要修前端测试或组件** — 那是症状不是根因
- **修后端 resolver/mutation** — 让它正确返回数据或处理错误
- 如果 review-ai 同时报了 blocking issue（如事务违反 Result 契约），
  那个就是根因，修它就能同时解决 E2E 失败

## GraphQL Schema 构建错误（"Unknown field" / "Unknown type"）
当 CI 报以下错误时，根因是 **GraphQL schema 构建时字段/类型未注册**，不是 resolver 逻辑问题：

```
Unknown field "valueStreamsBySpace" on type "Query". Did you mean "valueStreams"?
Unknown field "spaceById" on type "Query".
Unknown field "visibility" on type "Organizations".
```

### 诊断步骤
1. 找到 `build_graphql_schema` 函数（通常在 `graphql.rs` 或类似文件）
2. **`Unknown field "X" on type "Query"`** → X 是自定义 query，检查：
   - 是否调用了注册自定义 query 的函数（如 `register_space_scoped_queries`）
   - 该函数是否把 field push 到了 `builder.queries`
   - field 的返回类型（TypeRef）是否拼写正确
3. **`Unknown field "X" on type "Organizations"`**（实体类型缺字段）→ 检查：
   - SeaORM Entity Model 是否有该字段（如 `visibility: SpaceVisibility`）
   - 该字段的类型（如 `SpaceVisibility` enum）是否通过
     `builder.register_enumeration::<SpaceVisibility>()` 注册
   - seaography 自动注册实体字段时，如果字段类型（enum）未注册，
     该字段会被 **静默跳过** — 这是最常见的坑
4. **`Unknown type "X"`** → enum/struct 类型未注册，用
   `builder.register_enumeration::<X>()` 或 `builder.register_output_type::<X>()`

### 常见修复模式
```rust
// 在 build_graphql_schema 中，schema_builder().finish() 之前：
// 1. 注册所有被实体字段引用的 enum
builder.register_enumeration::<SpaceVisibility>();
builder.register_enumeration::<SpaceRole>();
// 2. 确保自定义 query 注册函数被调用
register_space_scoped_queries(&mut builder, ...);
```

### 验证修复
修完后，用 GraphQL introspection 确认字段存在：
```bash
curl -s http://localhost:8080/graphql -H 'Content-Type: application/json' \
  -d '{"query":"{ __type(name:\"Query\") { fields { name } } }"}' | python3 -m json.tool
curl -s http://localhost:8080/graphql -H 'Content-Type: application/json' \
  -d '{"query":"{ __type(name:\"Organizations\") { fields { name } } }"}' | python3 -m json.tool
```

### "Authentication required for mutations" 错误
当 CI 同时报 `Unknown field` 和 `Authentication required for mutations` 时：
1. **通常 `Unknown field` 是根因** — 前端查询失败后，错误处理逻辑尝试用 mutation
   记录错误，但 mutation 需要 auth → 产生二次错误。修好 schema 后此错误通常消失。
2. 如果修好 schema 后仍报此错误，检查后端 GraphQL auth guard：
   - 是否对 query 和 mutation 使用了不同的 auth 中间件
   - 测试用户（如 CI 中的 seed user）是否有足够的权限
   - auth guard 是否误拒了合法请求（如 token 解析逻辑有 bug）

## 集成测试本地复现
当单元测试通过但 CI 集成/E2E 测试失败时，**必须在本地复现失败**才能有效修复。
你有 terminal 和 docker 权限。步骤：

1. **启动后端**（在仓库根目录）：
   ```bash
   docker compose -f docker-compose.ci.yml up -d --build
   # 等待后端健康
   for i in $(seq 1 60); do curl -sf http://localhost:8080/health && break; sleep 2; done
   ```
2. **安装 Playwright**（在 frontend 目录）：
   ```bash
   cd frontend && npm install && npx playwright install-deps chromium && npx playwright install chromium
   ```
3. **运行 E2E 测试**（用 CI 相同的 filter）：
   ```bash
   npx playwright test --grep @smoke --reporter=line
   ```
4. **查看错误**：测试输出会显示 `GraphQL errors detected during test` 和具体的
   `Unknown field` 错误。`test-results/` 下有 `error-context.md` 和截图。
5. **迭代修复**：修后端代码 → 重新 build 后端 → 重跑 E2E：
   ```bash
   docker compose -f docker-compose.ci.yml up -d --build
   npx playwright test --grep @smoke --reporter=line
   ```
6. **完成后清理**：`docker compose -f docker-compose.ci.yml down`

> 注意：Rust 首次 build 可能需要 4-5 分钟。后续增量 build 会快很多。
> 如果 docker 不可用，至少用 GraphQL introspection（见上方）检查 schema。

## Rust 事务安全规则
当 `save()` 后跟 `audit_log()` 时，如果 audit_log 失败：
- ❌ 返回 Err（调用方认为操作未生效，但数据已入库）
- ✅ 用事务/补偿机制，或先写 audit log 再 save，或用 outbox pattern
