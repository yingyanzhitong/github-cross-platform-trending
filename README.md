# GitHub 跨平台热门软件日报

每天自动查找 GitHub 上同时支持 macOS 与 Windows 的热门软件，展示排名前 100 的项目，并生成可阅读的 Markdown 榜单和可二次处理的 JSON 数据。

## 工作方式

候选仓库来自：

1. GitHub Daily Trending；
2. 近期活跃的 `desktop-app`、`cross-platform`、`Electron`、`Tauri` 仓库；
3. 同时带有 `macos` 与 `windows` Topics 的仓库。

项目会读取候选仓库元数据与 Latest Release。只有 Latest Release 同时提供 macOS 的 `.dmg` 安装包（或文件名明确标注 macOS 的 `.pkg`）和 Windows 的 `.exe`/`.msi`/`.msix` 安装包，并判断它属于可使用的软件或工具时，才会进入榜单。仅在 README 声明支持双平台，或只有 `.zip`/`.tar.gz` 压缩包的项目不会入选。

入榜项目的英文简介会通过 GitHub Models 每 25 条一批生成简体中文简介，并按仓库与英文原文缓存到 `data/translations.json`。模型不可用时，报告仍会使用中文通用简介并记录采集警告，不会退回英文。

报告会将此前 7 天日报中从未出现过的仓库标记为醒目的 `🆕 NEW`。表格中的“查看详情”可定位到对应项目详情，详情中的“返回榜单中的本项目”可准确回到原表格行。

## 每日输出

- [`reports/latest.md`](reports/latest.md)：最新一期可读榜单；
- `reports/YYYY-MM-DD.md`：历史日报；
- `data/latest.json`：最新一期结构化数据；
- `data/YYYY-MM-DD.json`：历史结构化数据。

JSON 中同时保留 `description_en` 英文原文和 `description_zh` 中文简介。GitHub Actions 每天北京时间 08:30 自动运行，也支持在 Actions 页面手动触发。工作流使用仓库自带的 `GITHUB_TOKEN` 访问 GitHub API 与 GitHub Models，不需要额外配置密钥，并会将当天报告自动提交回仓库。

## 本地运行

需要 Python 3.10 或更高版本。已登录 GitHub CLI 时，脚本会自动读取当前认证；也可以设置 `GITHUB_TOKEN` 或 `GH_TOKEN`。

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
cross-platform-trending --limit 100 --max-candidates 1000
```

运行测试：

```bash
python -m unittest discover -s tests -v
```

## 筛选边界

GitHub 没有公开的 Trending API，也没有统一的跨平台软件元数据。本项目使用可复核的启发式规则，可能漏掉未在 README 或 Release 中清晰标注平台支持的项目。榜单不是 GitHub 官方推荐，也不替代对软件安全性、许可证与安装包签名的人工审查。
