# 权限设计原则

## 双层 RBAC

### [全局角色] UserRole: Admin / Architect / Viewer
- Admin：全权限，绕过所有 Space 级检查
- Architect：可 CRUD
- Viewer：只读
- **不要**：在业务代码中直接检查 `user.role == "admin"`，用 `ensure_can_xxx` 方法

### [Space 角色] SpaceRole: Owner / Editor
- Owner：管理成员 + 删除 + 编辑
- Editor：编辑内容
- Owner 隐含 Editor 权限（`is_editor()` 匹配 `Owner | Editor`）
- **不要**：在权限检查中遗漏 Owner 隐含 Editor 的关系

## 权限链路

### [三层守卫] 路由 → 组件 → API
- 路由层：ProtectedRoute 检查登录态，AdminRoute 检查 admin 角色
- 组件层：`useSpaceMembership(spaceId)` 返回 `canEdit`，控制按钮显示
- API 层：GraphQL 自定义查询用 membership-aware 查询
- **不要**：只在前端做权限检查（后端必须独立校验）

### [ensure_can_xxx] Service 层三级守卫
- `ensure_can_read`：公开空间任何人可读，私有空间需成员，Admin 绕过
- `ensure_can_edit`：需 Editor 或 Owner 或 Admin
- `ensure_can_manage`：需 Owner 或 Admin
- **不要**：在 GraphQL handler 中直接检查权限，通过 Service 层守卫方法

### [安全默认] 私有空间对非成员返回 SpaceNotFound
- 不返回 `NotSpaceMember`（防止泄露私有空间的存在）
- **不要**：用不同的错误码区分"空间不存在"和"无权访问"（都用 NOT_FOUND）

## Space 隔离

### [space_id 边界] 所有业务实体都有 space_id
- 自定义 query 先 `ensure_can_read(space_id)` 再按 space_id 过滤
- 按 ID 查询单条同时过滤 `id + space_id`
- 关联表创建验证两端属于同一 space
- **不要**：允许跨 space 的实体关联（如 cap_space != proc_space）

### [entity_guard] seaography 粗粒度守卫
- `USER_ENTITIES`：仅 Admin 可管理
- `PRIVATE_READ_ENTITIES`：需认证
- `ADMIN_READ_ENTITIES`：仅 Admin 可通过自动 query 读取
- `field_guard`：隐藏 `password_hash`、`token_hash`，限制 Admin-only 字段 `email`
- **不要**：对业务实体只靠 entity_guard（需要更细粒度的 space-level ACL）

### [owner_id 完备性] 所有实体必须有 owner_id，None 视为拒绝访问
- `ensure_entity_owner_or_admin` 在 `owner_id` 为 `None` 时对非管理员拒绝访问（fail-safe）
- 回填迁移必须覆盖所有有 owner 概念的实体表，不能只覆盖部分表
- 未回填的表会导致已存在的实体 owner_id 为 None，非管理员无法访问
- **不要**：在 owner_id 为 None 时放行非管理员（应 fail-safe 拒绝）

## 审计

### [审计操作] 先业务后审计
- 先持久化业务变更，再记录审计日志
- 审计失败不阻断业务（best-effort）
- **不要**：在权限检查通过前记录审计日志
