# 更新日志

本项目遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [0.3.1] - 2026-07-30

### 更新

- 更新 2026-07-30 跨平台热门软件前 100 榜单及结构化数据。
- 今日 Daily Trending 入榜项目为 GeoLibre 与 AIRI。
- 新增 Komi Store 与 Freeplane，移出 OpenHands 与 Hyper。
- 100 个项目均通过 macOS 与 Windows Latest Release 安装包校验。

## [0.3.0] - 2026-07-29

### 新增

- 榜单从前 20 扩展为前 100，表格和项目详情均完整展示。
- 新增 CLI、终端、生产力、笔记、音乐、下载、编辑器、开发工具和远程桌面候选来源。
- 新增大榜单中文简介分批生成测试。

### 变更

- 只有 Latest Release 同时提供 macOS 的 `.dmg`（或明确标注 macOS 的 `.pkg`）和 Windows 的 `.exe`/`.msi`/`.msix` 安装包才允许入榜。
- 每个 GitHub 搜索条件最多读取 100 个仓库，候选分析上限调整为 1000。
- 候选分析先检查 Release 安装包，通过双平台门槛后才读取 README。
- 报告平台证据只展示实际 Release 安装包，不再混入 README 文字证据。
- 候选仓库按热度分批分析，满足前 100 后停止继续请求。
- 中文简介改为每 25 条一批生成，降低单次模型输出压力。
- GitHub Actions 与本地运行示例同步改为前 100。

## [0.2.0] - 2026-07-29

### 新增

- 新增基于 GitHub Models 的批量中文简介生成。
- 新增 `data/translations.json` 中文简介缓存和模型失败时的中文兜底。
- JSON 数据新增 `description_en` 与 `description_zh` 字段。

### 变更

- `latest.md` 表格新增中文简介，项目详情不再展示英文简介。
- 项目详情中的 Stars 和 Forks 统计改为中文表述。
- GitHub Actions 新增最小化的 `models: read` 权限。

## [0.1.0] - 2026-07-29

### 新增

- 新增 GitHub Daily Trending 与近期热门仓库候选采集。
- 新增基于 README、Topics 和 Release 安装包的 macOS/Windows 双平台筛选。
- 新增 Markdown 日报与 JSON 结构化数据输出。
- 新增每天北京时间 08:30 自动运行并回写报告的 GitHub Actions 工作流。
- 新增核心解析、平台识别和报告渲染测试。
