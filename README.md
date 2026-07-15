# GitHub Stars

本仓库自动同步 GitHub 用户 [`434308421`](https://github.com/434308421) 当前 Star 的公开仓库。

<!-- stars:start -->
当前收录 **0** 个公开 Star 仓库，按 Star 时间倒序排列。

> 本区域由 GitHub Actions 自动生成，请勿手动编辑。

尚未同步到 Star 数据。
<!-- stars:end -->

## 同步机制

- GitHub Actions 每小时第 17 分钟检查一次，也支持在 Actions 页面手动运行。
- [`stars.json`](stars.json) 保存适合程序处理的结构化数据，本页保存便于浏览的明细表。
- 每次同步都以 GitHub 当前 Star 列表为准；取消 Star 后，对应仓库会在下次同步时移除。
- 仅在结果变化时提交，且不保存会频繁变化的仓库 Star 数，避免无意义提交。
- 同步脚本只使用 Python 标准库，不需要安装依赖或配置个人访问令牌。

## 本地验证

```powershell
python -m unittest discover -s tests -v
python -m py_compile scripts/sync_stars.py
```

本地直接执行同步会访问 GitHub API：

```powershell
$env:GITHUB_TOKEN = "<可选的 GitHub Token>"
python scripts/sync_stars.py --username 434308421
```

不要将真实 Token 写入仓库。GitHub Actions 运行时会使用仓库自动提供的 `GITHUB_TOKEN`。
