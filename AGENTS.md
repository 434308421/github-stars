# 项目概况

本仓库将 GitHub 用户 `434308421` 当前 Star 的公开仓库同步为 JSON 和 Markdown 明细。

## 用途

- `stars.json` 提供稳定、可机器读取的 Star 快照。
- `README.md` 提供按 Star 时间倒序排列的可阅读列表。
- 取消 Star 后，下次全量同步会移除对应记录。

## 技术栈

- Python 3，仅使用标准库
- GitHub REST API
- GitHub Actions
- Python `unittest`

## 目录结构

```text
.
├─ .github/workflows/sync-stars.yml  # 定时同步与自动提交
├─ scripts/sync_stars.py             # API 获取、规范化和渲染
├─ tests/test_project_configuration.py # 工作流配置契约测试
├─ tests/test_sync_stars.py          # 无网络单元测试
├─ README.md                         # 项目说明与生成的明细
└─ stars.json                        # 结构化快照
```

## 启动、测试和构建命令

```powershell
python -m unittest discover -s tests -v
python -m py_compile scripts/sync_stars.py
python scripts/sync_stars.py --username 434308421
```

本项目无构建步骤。最后一条命令会访问 GitHub API；本地需要更高限额时，通过环境变量 `GITHUB_TOKEN` 提供 Token，禁止写入文件。

## 核心模块

- `fetch_starred`：读取带 Star 时间的分页 API 数据。
- `build_snapshot`：选择稳定字段并按 Star 时间排序。
- `render_stars_section`：生成 README 表格。
- `synchronize`：协调获取、快照写入和 README 更新。

## 关键约定

- README 中 `stars:start` 与 `stars:end` 标记之间为自动生成区域，不手动编辑。
- 不保存 `stargazers_count`、`pushed_at` 或同步时间，避免数据未实质变化时产生提交。
- 全量快照代表当前状态，不保留已取消 Star 的历史记录。
- 不新增运行时依赖；若确有必要修改依赖策略，应先说明影响。

## 当前状态

已上线运行，并已通过 GitHub Actions 完成首次真实 Star 数据同步。

## 常见注意事项

- GitHub 定时任务不是实时触发，通常会有数分钟延迟。
- 工作流需要仓库允许 GitHub Actions 使用 `contents: write` 权限。
- 公开仓库长期无活动时，GitHub 可能停用定时工作流，可在 Actions 页面重新启用并手动运行。
