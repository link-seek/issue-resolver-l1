# 前端设计原则

## 组件模式

### [shadcn/ui 包装] Radix Primitive → forwardRef + CVA + Tailwind
- UI 原语放 `components/ui/`，业务组件放 `views/{domain}/` 同目录
- 不创建 `components/business/` 中间层
- 样式用 `cva()` 变体 + `cn()` 合并，不直接暴露 Radix primitive
- **不要**：在业务组件中内联 Radix primitive 而不经 `components/ui/` 包装

### [ConfirmDialog] 声明式确认对话框
- 受控模式：`open` + `onOpenChange`，不内部管理开关
- 支持 `loading`（阻止关闭）、`destructive`（红色按钮）、`error` prop（行内错误 `role="alert"`）
- **不要**：用 `window.confirm()` 或自建 Dialog 做删除确认

### [列表 memo] memo + 具名函数组件
- 列表渲染组件用 `memo(function Name() {})` 包裹
- props：`nodes`（数据）、`canEdit`（权限）、`isMobile`（响应式）
- **不要**：在列表组件内做数据获取，数据由父组件传入

## 状态管理

### [Zustand 全局] Zustand + localStorage 持久化
- 全局状态只用 Zustand，token 从 localStorage 初始化
- 组件中通过 selector 订阅：`useAuthStore((s) => s.token)`
- 非组件上下文用 `useAuthStore.getState()` 直接读取
- **不要**：用 React Context 管理全局状态

### [Apollo 服务端] Apollo Client errorPolicy: 'all'
- 所有业务数据通过 Apollo Client 获取
- `errorPolicy: 'all'` — partial data + error 同时返回
- Auth token 通过 `setContext` link 从 localStorage 注入
- **不要**：用 React Query 或 fetch 管理服务端状态

### [数据获取] useQuery + useMutation + refetchQueries
- useQuery：页面级数据，配合 `skip` 条件跳过
- useMutation：通过 `refetchQueries` 刷新列表（不用 cache.modify/update）
- useLazyQuery：按需查询（如用户搜索）
- **不要**：用 useSuspenseQuery，手动处理 loading/error

## 错误处理

### [三级错误] 行内 banner → ConfirmDialog error → console.error
- CRUD Dialog：mutation catch 后 `setError(err.message)`，顶部 `bg-destructive/10` 红色 banner
- ConfirmDialog：通过 `error` prop，`role="alert"` + `aria-live="assertive"`
- 删除/归档失败：`console.error` 吞掉，不展示给用户
- 列表加载失败：`{Boolean(error) && <div className="text-destructive">加载失败</div>}`
- **不要**：用 toast 通知库，全部用行内错误
- **不要**：直接渲染 `error.message` 给用户，用 `extractFriendlyError()` 转友好提示

### [友好错误] extractFriendlyError 模式
- 正则匹配 network/timeout → "网络错误，请检查连接"
- 匹配 unauthorized/forbidden → "权限不足"
- 兜底 → "操作失败，请稍后重试"
- **不要**：把 GraphQL 原始 error message 直接展示给用户

## 表单模式

### [受控表单] useState 受控组件
- 每个字段一个 `useState`，通过 `value` + `onChange` 绑定
- 编辑时 `useEffect` 在 dialog 打开时回填
- 提交：`try { await mutation(); onOpenChange(false) } catch { setError(...) }`
- 禁用条件：`disabled={loading || !name.trim()}`
- **不要**：虽然已安装 react-hook-form + zod，但当前约定是 useState 手动管理

### [表单布局] Label + Input 垂直堆叠
- `<div className="space-y-2"><Label>...</Label><Input .../></div>`
- 枚举字段用原生 `<select>` + Tailwind（非 Radix Select）
- 多列：`grid grid-cols-1 sm:grid-cols-2 gap-4`
- Dialog 内：`space-y-4 py-4`

## 响应式

### [移动端/桌面端] useIsMobile + 条件渲染双布局
- `useIsMobile(768)` 基于 `window.matchMedia`，同步初始值避免闪烁
- 移动端：卡片列表 + DropdownMenu 操作
- 桌面端：Table + 行内按钮操作
- **不要**：用 CSS `hidden md:block` 切换组件，用条件渲染（`if (isMobile) return <Mobile/>`）
- **不要**：移动端和桌面端状态不一致（如移动端有 disabled 但桌面端没有）

### [移动端 DropdownMenu] disabled prop 必须传递
- DropdownMenuItem 的 disabled 状态在移动端和桌面端必须一致
- 权限不足时 `disabled={!canEdit}` 要同时应用到卡片菜单和表格按钮

## 路由

### [路由组织] createBrowserRouter + lazy + 嵌套布局
- 所有页面 `lazy: async () => ({ Component: (await import(...)).default })`
- ProtectedRoute → ArchLayout → 子页面 三层嵌套
- **不要**：静态 import 页面组件（破坏代码分割）

### [目录结构] views 按业务域分目录
- `views/{domain}/layout.tsx` + `crud.tsx` + 主页面
- `api/` GraphQL 操作 + 类型（按域分文件）
- `stores/` Zustand store
- `hooks/` 自定义 hook

## 类型安全

### [手写类型] interface + GraphQL Fragment 双轨
- 未使用 GraphQL Code Generator，类型手写
- 共享类型放 `api/spaces.ts`，页面级类型在页面文件内定义
- **不要**：在多个文件重复定义同一类型（如 ValueStream 在 crud.tsx 和 version-control.tsx 各定义一次）

## 可访问性

### [a11y] 依赖 Radix 内建 + 显式标注
- 图标按钮加 `aria-label`
- 加载指示器加 `<span className="sr-only">加载中</span>`
- 错误提示用 `role="alert"` + `aria-live="assertive"`
- **不要**：额外添加 aria 属性覆盖 Radix 默认行为

## 认证

### [双通道] REST (auth) + GraphQL (business)
- 认证操作（login/logout/fetchMe）用 REST API（fetch）
- 业务数据用 GraphQL（Apollo Client）
- **不要**：用 GraphQL 做认证操作
