---
name: git-dual-remote-push
description: GitHub 和 Gitee 双远程推送配置，每次提交后必须两边都推
metadata:
  type: project
---

本项目配置了两个 Git 远程仓库，**每次 commit 后必须推送到两个平台**，不能只推一个。

## 远程地址

| Remote | 平台 | 地址 |
|--------|------|------|
| `origin` | GitHub | `git@github.com:ygttygtt/SectorBreaker.git` |
| `gitee` | Gitee | `git@gitee.com:ygttygtt/sector-breaker.git` |

## 推送命令

```bash
git push origin main && git push gitee main
```

## 注意事项

- GitHub 使用 SSH 协议，由 `gh` CLI 管理认证
- Gitee 同样使用 SSH，已配置好密钥
- 两个平台都用 `main` 作为默认分支
- **Why:** 用户同时维护 GitHub 和 Gitee 两个代码托管平台，确保代码同步备份
- **How to apply:** 每次执行 `git commit` 后，立即推送到两个远程；不要只推 origin 就结束
