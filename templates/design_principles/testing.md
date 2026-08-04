# 测试设计原则

## E2E 测试

### [标签分层] @smoke 必须标注
- `@smoke`：CI 必跑（PR CI + Merge CI + Deploy Smoke）
- 无标签：完整功能测试，仅本地/手动跑
- CI 通过 `--grep @smoke` 过滤
- **不要**：新增 E2E 测试不加 `@smoke` 标签（CI 中不会跑，等于没有回归保护）

### [凭证管理] env 驱动 + auth.ts helper
- 凭证从 `helpers/auth.ts` 导出：`TEST_EMAIL`、`TEST_PASSWORD`、`TEST_SPACE_ID`
- 默认值适用于本地开发，CI/生产通过 `E2E_TEST_EMAIL` 等环境变量覆盖
- 登录用 `login(page)` helper，不用手动填表单
- **不要**：在测试文件中硬编码凭证（如 `test@example.com` / `testpassword123`）
- **不要**：在 beforeEach 中手动写登录逻辑，用 `login(page)` helper

### [GraphQL-aware] 自动检测 GraphQL 错误
- `import { test, expect } from '../helpers/graphql-aware'`（替代 `@playwright/test`）
- 自动拦截 `/graphql` 和 `/api` 响应，收集 `body.errors`
- 测试结束后如有 GraphQL 错误则抛异常
- **不要**：直接 `import { test, expect } from '@playwright/test'`（不会检测 GraphQL 错误）

### [Playwright 配置] 串行单 worker
- `fullyParallel: false` + `workers: 1`（避免数据冲突）
- `timeout: 30_000`，`trace: "on-first-retry"`
- baseURL 三态：`E2E_BASE_URL` env → CI `localhost:80` → 本地 `localhost:3000`
- **不要**：用 parallel/workers > 1（测试间有数据依赖）

## 后端测试

### [Migration 测试] sqlite::memory: + Migrator::up
- 连接内存数据库，运行全部迁移
- 插入测试行（省略新增列），验证列存在、默认值
- 更新为非 NULL 值，验证可读写
- **不要**：用真实数据库做 migration 测试（用 `sqlite::memory:`）

### [单元测试] Fake Repository + in-memory
- 用 `HashMap` + `Arc<Mutex>` 实现 Fake Repository，满足 Repository trait
- 测试真实 Service 的授权逻辑（非 mock）
- Fake 之间共享 store 以支持跨 repo 查询
- **不要**：mock Repository trait（用 Fake 实现测试真实逻辑）

## CI

### [PR CI] 只跑 @smoke
- `e2e-filter: '--grep @smoke'`
- backend: `cargo test --workspace`
- frontend: `npx vite build`
- integration: docker-compose.ci + Playwright @smoke
- **不要**：在 PR CI 跑全量 E2E（太慢）

### [覆盖率检查] PR 修改源码时检查对应测试
- coverage-mappings 配置源码模式 → 测试目录映射
- 修改 `frontend/src/views/spaces/` → 检查 `tests/spaces/` 有无测试
- `human-review-paths` 排除 `backend/migration/**`
- **不要**：新增源码不新增测试（覆盖率检查会报）
