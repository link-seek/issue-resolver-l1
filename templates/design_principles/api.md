# API 设计原则

## GraphQL Mutation

### [命名] Entity+Action camelCase
- 格式：`{entityName}{Action}`
- Action 词汇：Create / Update / Archive / Delete / CreateVersion / SetVisibility / AddMember / RemoveMember
- **不要**：用通用 `delete`，用 `archive` 表达业务语义
- **不要**：把特殊操作塞进 Update（如 visibility 改动用独立 `spaceSetVisibility` mutation）

### [参数] 扁平参数（非 Input Object）
- 直接 `.argument(InputValue::new(...))` 逐个声明
- 必填用 `TypeRef::named_nn()`，可选用 `TypeRef::named()`
- UUID 以 String 传入后 `parse_uuid_arg()` 转换
- **不要**：创建 GraphQL Input Object 类型（当前约定是扁平参数）

### [双轨 Schema] seaography 自动 CRUD + 手动 Domain Mutation
- 用户管理实体：`register_entity_with_mutations`（seaography 全自动 CRUD）
- 业务架构实体：`register_entity`（仅自动 query）+ 手动注册 domain mutation
- 原因：业务 mutation 需要 space-level ACL，seaography 的 entity_guard 只做粗粒度角色检查
- **不要**：对业务实体用 seaography 自动 mutation（无法做行级权限）

## 错误响应

### [extensions.code] 语义码
- DomainError 映射到 GraphQL Error + extensions.code：
  - `FORBIDDEN_SPACE_NOT_MEMBER` / `FORBIDDEN_SPACE_NOT_EDITOR` / `FORBIDDEN_SPACE_NOT_OWNER`
  - `SPACE_QUOTA_EXCEEDED` / `NOT_FOUND` / `VALIDATION_ERROR` / `INTERNAL_ERROR`
- Database/AuditLog 错误：服务端 log 完整消息，客户端只收 `"Internal server error"`
- **不要**：把数据库错误消息直接返回给客户端（信息泄露）

### [错误传播] DbErr → DomainError → GraphQL Error
- `From<sea_orm::DbErr>` 自动转换
- `domain_err_to_graphql()` 做映射 + extensions.code
- 敏感信息过滤：Database 和 AuditLogFailed 仅 `tracing::error!` 记录
- 业务错误原样传播
- **不要**：在 GraphQL handler 中直接 match DbErr（应该让 DomainError 做转换）

## 查询

### [自定义查询] membership-aware
- 用自定义查询（`spaces`/`spaceById`）而非 seaography 自动生成查询
- seaography 自动查询需要 admin 权限，不适合普通用户
- 按 ID 查询单条时同时过滤 `id + space_id`，防止跨空间越权
- **不要**：用 seaography 自动 query 做业务数据查询（权限不够细）
