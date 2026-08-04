# 后端设计原则

## DDD 分层

### [三层分离] domain → application → infrastructure
- `domain/` 零外部依赖（仅 uuid/chrono/shared-common）
- `application/` 依赖 `domain`，仅做编排，不含业务逻辑
- `infrastructure/` 依赖 `domain` + SeaORM
- **不要**：domain 依赖 infrastructure（依赖方向：infrastructure → domain ← application）

### [聚合模块化] 每个聚合根一个子模块
- `domain/{aggregate}/entity.rs` + `repository.rs` + `mod.rs`
- 跨聚合引用仅通过 `Uuid` ID，不持有其他聚合的实体引用
- **不要**：在一个聚合的 entity 中 import 另一个聚合的 entity

### [调用链路] GraphQL → Service → Domain Entity → Repository
- Service 不包含业务逻辑（注释："No business logic here — all rules live in the domain model"）
- Service 仅做编排：调用 Entity 方法 + Repository 持久化
- GraphQL handler 中的写操作（含 transfer ownership 等）必须通过 Service 层，不能直接调用 `repo.update(db)`
- 直接绕过 Service 层会丢失审计日志、领域校验和事件发布
- 重复的 handler 逻辑应提取为共享辅助函数
- **不要**：在 GraphQL handler 或 Service 中写业务规则
- **不要**：在 GraphQL handler 中直接调用 Repository 的 update/save 绕过 Service 层

## 实体设计

### [充血模型] Entity struct 纯数据 + impl 行为方法
- `#[derive(Debug, Clone, PartialEq)]` 纯数据 struct，所有字段 `pub`
- 业务行为通过 `impl` 方法：`create()`、`rename()`、`archive()` 等
- 每个行为方法精确修改相关字段并自动更新 `updated_at`
- **不要**：给字段设 setter，用行为方法表达意图

### [create 工厂] 关联函数 + 领域验证
- `create()` 返回 `Result<Self, DomainError>`，构造时执行验证
- `id` 由调用方传入（`Uuid::now_v7()`），`now` 时间注入便于测试
- `deleted_at` 初始化为 `None`
- **不要**：在 Service 层做实体验证，验证在 Entity::create 中

### [Option-patch 更新] 每个可变参数 Option<T> 包装
- `None` = 不修改，`Some(value)` = 设新值
- `Option<String>` 字段用 `Option<Option<String>>`：外层 None=不改，Some(None)=清空，Some(Some(v))=设值
- 先检查状态守卫（如 `status != Active`），再逐字段应用
- **不要**：用全量覆盖更新（会丢失未传字段的值）

### [默认值] 领域默认值 vs 数据库默认值分离
- 领域层 `create()` 显式设置默认值
- Rust `Default` trait 用最小权限原则（`SpaceVisibility::default() = Private`）
- 数据库列默认可不同（向后兼容），两者故意不同防止遗漏时意外公开
- **不要**：依赖数据库 default 做业务默认值

## 聚合根

### [聚合根列表] Space, ValueStream, BusinessCapability, BusinessProcess
- 每个聚合根有独立 Repository trait
- 子实体（ProcessStep, ValueStreamStage, SpaceMember）通过父 ID 关联
- 子实体生命周期依赖父实体
- **不要**：让子实体独立于父实体存在

### [外键 ID 引用] 不持有对象引用
- 子实体持有父聚合的 `Uuid` ID（如 `process_id`、`space_id`）
- 所有实体都有 `space_id` 实现多租户隔离
- **不要**：在实体 struct 中持有其他实体的引用

### [级联操作] 显式级联 + 空间隔离守卫
- 关联表创建必须验证两端属于同一 space（`cap_space == proc_space`）
- 关联创建前验证双方都是 Active 状态
- 删除父实体不自动级联（用 soft delete）
- **不要**：允许跨 space 的实体关联

## Repository

### [依赖倒置] trait 在 domain 层，实现在 infrastructure 层
- `#[async_trait]` 定义 trait，返回 `Result<T, DomainError>`
- SeaORM 实现 + `From<Model>` 转换
- **不要**：在 domain 层 import sea_orm

### [幂等 save] find-then-insert-or-update
- `save()` 先 `find_by_id`，存在则 update，不存在则 insert
- **不要**：用 raw insert（会主键冲突）

### [软删除] deleted_at 字段
- `soft_delete()` 设 `deleted_at = Some(now)`，查询默认过滤 `deleted_at.is_null()`
- `archive()` 是状态转换（Active → Archived），`soft_delete()` 是逻辑删除
- 两者独立：归档不删除，删除不归档
- **不要**：用物理删除（除非有明确的数据合规要求）

### [分页] Offset Pagination
- 返回 `(Vec<Entity>, total_count)` 元组
- `PageInput` 默认 page=1, per_page=20
- **不要**：返回裸 Vec 不带总数

### [事务] 显式事务包裹批量操作
- `save_batch()` 用 `db.begin()` + 循环 save + `txn.commit()`
- 单条 save 不用事务
- 版本创建用事务包裹归档旧版 + 插入新版
- **不要**：在循环中逐条 save 不用事务（部分失败会数据不一致）

### [DB 唯一约束] 唯一性由数据库保证，不靠应用层 check-then-act
- 唯一约束（如 sequence_order 唯一）必须在数据库层面用 UNIQUE INDEX 保证
- 应用层先检查再插入（check-then-act）存在竞态：两个并发请求同时通过检查
- 应用层检查仅用于友好的错误提示，真正的唯一性保证靠 DB 约束
- 插入时捕获 DB 唯一约束冲突错误，映射为语义正确的 DomainError（如 `Conflict` / `DuplicateSequenceOrder`）
- **不要**：仅靠应用层 check-then-act 保证唯一性（并发下会失效）

### [错误传播] 不静默丢弃错误
- `serde_json::from_str` / `to_string` 失败时用 `map_err` 转为 DomainError，不用 `.ok()` 或 `unwrap_or_default()`
- 迁移中 `ALTER TABLE ADD COLUMN` 的幂等性靠匹配特定错误码（如 "column already exists"），不用 `let _ =` 吞掉所有错误
- 无效输入（如 `Uuid::parse_str` 失败）返回明确的 DomainError，不用 `.ok()` 静默转为 None
- **不要**：用 `.ok()` / `unwrap_or_default()` / `let _ =` 静默丢弃序列化/解析/SQL 错误（会隐藏数据损坏）

### [迁移后端无关] 迁移代码不硬编码数据库后端
- 查询和操作使用后端无关的 API（`db.execute_unprepared()`），不硬编码 `DatabaseBackend::Sqlite`
- 如需后端特定逻辑，用 `match db.get_database_backend()` 分支处理所有后端
- **不要**：在迁移中硬编码单一后端（会导致其他后端如 PostgreSQL/MySQL 执行失败）

## 版本管理

### [三标识] id + logical_id + business_version
- `id`：物理主键，每版本唯一
- `logical_id`：逻辑身份，跨版本相同
- `business_version`：语义版本号如 "v1.0"
- 首版约定：`logical_id = id`
- **不要**：用自增整数做版本号，用 semver

### [Copy-on-Write 版本化] 归档旧版 + 插入新版（事务内）
- 验证当前版本是 Active → archive(now) → 构造新版本 → save_batch 事务
- 版本号通过 `bump_minor()` 递增（semver minor bump）
- **不要**：原地修改已发布版本

### [状态机] Active → Archived 单向
- Active → Archived：合法（通过 `archive()`）
- Archived → Active：禁止
- Archived 状态下不可修改（update/create_new_version 都检查 status）
- **不要**：允许从 Archived 回到 Active

## 值对象

### [Newtype] 验证 + 类型安全
- newtype wrapper 包裹原始类型，构造时验证
- 实现 Display、AsRef<str> 等标准 trait
- **不要**：用裸 String 表达有约束的值（如 Email、SpaceAuditAction）

### [JSON 值对象] SeaORM FromJsonQueryResult
- `StringVec(Vec<String>)` 用于列表字段
- `StringStringMap(HashMap<String, String>)` 用于键值对字段
- **不要**：用 JSON string 手动序列化

## 审计日志

### [Best-effort] 先业务后审计
- 先持久化业务变更，再记录审计日志
- 审计失败不导致业务失败（不返回 Err）
- strict 模式 `tracing::error!`，非 strict `tracing::warn!`
- **不要**：让审计失败阻断业务操作

## ID 生成

### [UUIDv7] 时间排序主键
- `Uuid::now_v7()` 兼顾唯一性和 B-tree 友好性
- ID 在 Service 层生成后传入 Entity::create()
- **不要**：用数据库自增 ID
