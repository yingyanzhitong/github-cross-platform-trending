# 更新日志

本项目遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

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
