## 项目设计原则

（由 L2 分析 OCR findings 后自动注入。L1 修复代码时应遵循这些原则。）

## 跨文件一致性原则

当 review-ai 报告「X 文件的默认值与 Y 文件不一致」时，**必须同时读取并修复所有相关文件**，使它们使用相同的值。只改一个文件会导致下一轮 review-ai 再次报告不一致（振荡）。

### APP_ENV 默认值（安全优先）

- [config.rs:84 load()] APP_ENV 未设置时应默认为 `"production"`，不是 `"local"`。
  原因：最小权限原则 — 部署环境忘记设置 APP_ENV 时，应以最安全的模式运行（要求显式配置 JWT secret），而非静默生成弱密钥。
- [config.rs:106 ensure_defaults()] 同上，APP_ENV 默认值必须为 `"production"`，与 load() 和 state.rs 保持一致。
- [state.rs:47,143,187] 已正确默认为 `"production"`，无需修改。
- **关键**：config.rs 的 load() 和 ensure_defaults() 两处 APP_ENV 默认值都必须改为 `"production"`。
  开发者在本地开发时需显式设置 `APP_ENV=local`（显式优于隐式原则）。
- 修复时用不区分大小写的比较（如 `eq_ignore_ascii_case`），避免 `APP_ENV=Production` 被误判为非生产环境。
