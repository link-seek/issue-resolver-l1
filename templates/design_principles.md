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

## 前端错误展示原则（安全优先）

- 禁止将 `error.message`、`queryError.message` 或任何 GraphQL/API 错误原始信息直接渲染给用户。
- 应使用通用提示如 `加载失败，请稍后重试`，并用 `console.error` 记录原始错误。
- 项目已有正确范例：`capabilities.tsx`、`processes.tsx`、`value-streams.tsx` 中的错误处理均使用此模式。
- 只修 review-ai 报告的位置，不主动扩大范围。

## 移动端/桌面端状态一致性原则

- Radix UI `DropdownMenuItem` 支持 `disabled` 属性（Primitive 透传 props，组件已含 `data-[disabled]` 样式）。
- 桌面端有 `disabled={someLoading}` → 移动端对应项必须加同样的 `disabled`。
- 同理，`loading` 状态保护也必须一致。
- ❌ 错误：`<DropdownMenuItem onClick={...}>删除</DropdownMenuItem>`（无 disabled）
- ✅ 正确：`<DropdownMenuItem disabled={archiveLoading || visibilityLoading} onClick={...}>删除</DropdownMenuItem>`
