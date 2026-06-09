# Git 使用指南
> 面向电力系统生产模拟团队 · PyCharm + Git 环境

---

## 目录

1. [Git 是什么，为什么用它](#1-git-是什么为什么用它)
2. [安装与初始配置](#2-安装与初始配置)
3. [核心概念（必须懂的五个词）](#3-核心概念必须懂的五个词)
4. [克隆仓库，从这里开始](#4-克隆仓库从这里开始)
5. [每天开发的标准流程](#5-每天开发的标准流程)
6. [PyCharm 里的 Git 操作图解](#6-pycharm-里的-git-操作图解)
7. [分支：多人协作的核心](#7-分支多人协作的核心)
8. [Commit：记录你做了什么](#8-commit记录你做了什么)
9. [Push 与 Pull：和远端同步](#9-push-与-pull和远端同步)
10. [Pull Request：申请合并代码](#10-pull-request申请合并代码)
11. [冲突：遇到了怎么解决](#11-冲突遇到了怎么解决)
12. [常见问题与急救手册](#12-常见问题与急救手册)
13. [本项目的 Git 规则速查](#13-本项目的-git-规则速查)
14. [PyCharm 中本项目常用 Git 操作命令](#14-pycharm-中本项目常用-git-操作命令)

---

## 1. Git 是什么，为什么用它

### 没有 Git 会发生什么

想象四个人同时修改同一份 `simulator.py`：

- 小张做完储能模块，用微信把文件发给小李
- 小李改了调度逻辑，直接覆盖保存，小张的储能代码消失了
- 出了 bug，没人知道是谁改的、什么时候改的、改了哪里
- 想回退到昨天的版本，发现没有备份

**Git 解决的就是这些问题。**

### Git 做了什么

```
每次你提交代码，Git 就给当前状态拍一张"快照"，并记录：
  - 谁改的（作者）
  - 什么时候改的（时间戳）
  - 改了哪些文件的哪些行（diff）
  - 为什么改（你写的 commit 信息）

多人协作时，Git 负责把各自的修改合并起来，发现冲突时提醒你手动解决。
```

---

## 2. 安装与初始配置

### 2.1 安装 Git

**Windows：**
前往 https://git-scm.com/download/win 下载安装包，一路默认即可。安装完成后，在开始菜单里能找到 "Git Bash"。

**macOS：**
打开终端，输入 `git --version`，如果没有安装，系统会提示自动安装开发者工具。

**验证安装：**
打开终端（Windows 用 Git Bash 或 PowerShell），输入：
```bash
git --version
```
看到版本号（如 `git version 2.43.0`）说明安装成功。

---

### 2.2 配置你的身份（只需做一次）

Git 每次提交都会记录"谁提交的"，所以要先告诉它你是谁。

打开终端，执行以下两条命令（替换成你自己的信息）：

```bash
git config --global user.name "张三"
git config --global user.email "zhangsan@example.com"
```

> **注意**：邮箱必须和你 GitHub 账号的注册邮箱一致，否则 GitHub 上不会显示你的提交记录。

验证配置：
```bash
git config --global --list
```

---

### 2.3 在 PyCharm 中配置 Git

1. 打开 PyCharm，进入 `File → Settings`（macOS 是 `PyCharm → Preferences`）
2. 找到 `Version Control → Git`
3. 确认 `Path to Git executable` 已自动填充（通常是 `C:\Program Files\Git\bin\git.exe` 或 `/usr/bin/git`）
4. 点击 `Test` 按钮，看到版本号即为成功

---

### 2.4 配置 SSH 密钥（推荐，避免每次输密码）

**第一步：生成密钥**
```bash
ssh-keygen -t ed25519 -C "你的邮箱@example.com"
```
一路回车（不需要设置密码短语）。密钥会保存在 `~/.ssh/id_ed25519.pub`。

**第二步：查看公钥**
```bash
cat ~/.ssh/id_ed25519.pub
```
复制输出的全部内容（以 `ssh-ed25519` 开头）。

**第三步：添加到 GitHub**
1. 登录 GitHub → 右上角头像 → `Settings`
2. 左侧菜单 `SSH and GPG keys` → `New SSH key`
3. Title 填写电脑名称（方便识别），Key 粘贴刚才复制的内容
4. 点击 `Add SSH key`

**验证：**
```bash
ssh -T git@github.com
```
看到 `Hi 用户名! You've successfully authenticated` 即为成功。

---

## 3. 核心概念（必须懂的五个词）

在开始操作之前，先理解这五个词，后面所有操作都围绕它们展开。

### 仓库（Repository / Repo）

存放项目所有文件和历史记录的地方。有两种：

- **本地仓库**：在你电脑上的那份，你在这里写代码
- **远端仓库**：在 GitHub 服务器上的那份，团队共享

### 分支（Branch）

可以把分支理解成项目的"平行时间线"。

```
main ────●────●────●────●────────── （稳定版本）
              │
dev      ─────●────●────●────────── （集成开发）
                   │
feature/storage ───●────●────PR──►  （你在做的功能）
```

每个人在自己的 feature 分支上开发，互不干扰。开发完成后再合并到 dev。

### 提交（Commit）

一次快照。每个 commit 记录了从上次到这次你改了什么，是 Git 历史的最小单位。

### 暂存区（Staging Area）

提交前的"待发货区"。你修改了三个文件，可以只把其中两个放入暂存区，只提交这两个。

```
工作区（你写代码的地方）
     │  git add
     ▼
暂存区（选择要提交的内容）
     │  git commit
     ▼
本地仓库（记录快照）
     │  git push
     ▼
远端仓库（GitHub，团队共享）
```

### 合并（Merge / Pull Request）

把一个分支的改动合入另一个分支。在 GitHub 上通过 Pull Request（PR）申请合并，经过 Code Review 后才正式合入。

---

## 4. 克隆仓库，从这里开始

"克隆"就是把 GitHub 上的远端仓库完整复制到你的电脑上。**每人只需做一次。**

### 方法一：命令行

```bash
# 进入你想存放项目的目录
cd D:/projects    # Windows
# 或
cd ~/projects     # macOS/Linux

# 克隆仓库（SSH 方式，需要配置过 SSH 密钥）
git clone git@github.com:你的组织/项目名.git

# 或者 HTTPS 方式（不需要 SSH，但每次要输密码）
git clone https://github.com/你的组织/项目名.git
```

克隆完成后，进入项目目录：
```bash
cd 项目名
```

### 方法二：PyCharm 图形界面

1. 打开 PyCharm，选择 `Get from VCS`（或 `File → New → Project from Version Control`）
2. 在 URL 栏粘贴仓库地址
3. 选择本地存放路径
4. 点击 `Clone`

---

## 5. 每天开发的标准流程

这是你每天开始工作时应该执行的步骤，形成习惯后不会超过 2 分钟。

### 开始工作前（同步最新代码）

```bash
# 1. 切换到 dev 分支
git checkout dev

# 2. 拉取最新代码（获取队友昨天的提交）
git pull

# 3. 切换到你的功能分支
git checkout feature/你的功能名

# 4. 把 dev 的最新内容合并进你的分支（保持同步）
git merge dev
```

**为什么每天都要做第 4 步？**
如果你三天没有合并 dev 的更新，而队友这三天改了很多基础代码，到时候合并会产生大量冲突，非常痛苦。每天合并一次，每次冲突量极少，解决起来很轻松。

---

### 开发过程中（阶段性提交）

不要等到功能全部完成才提交。建议每完成一个小功能点就提交一次。

```bash
# 查看哪些文件被修改了
git status

# 把修改的文件添加到暂存区
git add src/simulation/storage.py          # 添加单个文件
git add src/simulation/                     # 添加整个目录
git add .                                   # 添加所有修改（慎用）

# 提交，并写清楚做了什么
git commit -m "feat(storage): add SOC update with efficiency"
```

**提交频率建议：**
- 完成一个函数并通过手算验证 → 提交一次
- 修复了一个 bug → 提交一次
- 不要把"写了 storage.py 的全部内容"放在一个 commit 里

---

### 结束工作后（推送到远端）

```bash
git push origin feature/你的功能名
```

这样即使你的电脑坏了，代码也在 GitHub 上安全保存着。

---

## 6. PyCharm 里的 Git 操作图解

PyCharm 内置了完整的 Git 图形界面，大多数操作不需要命令行。

### 查看文件状态

PyCharm 会用颜色标记文件状态：

| 颜色 | 含义 |
|------|------|
| **绿色** | 新文件，已加入 Git 跟踪（已 add） |
| **蓝色** | 已跟踪的文件被修改，尚未提交 |
| **红色** | 未被 Git 跟踪的新文件 |
| **灰色** | 被 `.gitignore` 忽略的文件 |

### 提交（Commit）

**方式一：快捷键**
`Ctrl + K`（macOS `Cmd + K`）打开 Commit 面板。

**步骤：**
1. 在左侧勾选要提交的文件（相当于 `git add`）
2. 在下方文本框写 commit 信息
3. 点击 `Commit` 按钮（只提交到本地）或 `Commit and Push`（提交并推送到远端）

### 推送（Push）

`Ctrl + Shift + K`（macOS `Cmd + Shift + K`）打开 Push 对话框，确认分支和提交后点击 `Push`。

### 拉取（Pull）

菜单栏 `Git → Pull`，或者直接点击右下角分支名旁边的 ↓ 图标。

### 切换分支

点击 PyCharm 右下角的分支名（例如 `feature/storage`），在弹出菜单中选择要切换的分支，点击 `Checkout`。

### 查看提交历史

菜单栏 `Git → Show Git Log`（或 `Alt + 9` 快捷键），可以看到所有提交记录的图形化展示，包括每次改了哪些文件、每行的变化。

---

## 7. 分支：多人协作的核心

### 本项目的分支结构

```
main        ── 稳定版本，只有负责人能合并，始终可运行
  │
dev         ── 集成开发，PR 审核通过后合并进来
  │
feature/xxx ── 每人自己的功能分支，在这里写代码
fix/xxx     ── bug 修复分支
```

### 创建功能分支

**命令行：**
```bash
# 先确认在 dev 上，且是最新代码
git checkout dev
git pull

# 创建并切换到新分支
git checkout -b feature/storage-soc-update
```

**PyCharm：**
右下角点击分支名 → `+ New Branch` → 输入分支名 → 确认基于 `dev` 创建。

### 分支命名规则

| 类型 | 格式 | 示例 |
|------|------|------|
| 新功能 | `feature/功能名` | `feature/storage-soc-update` |
| Bug 修复 | `fix/问题描述` | `fix/power-balance-error` |
| 文档更新 | `docs/内容描述` | `docs/add-api-readme` |

**只用英文和连字符，不用空格和中文。**

### 删除已合并的分支

PR 合并后，你的功能分支就完成使命了，可以删除：

```bash
# 删除本地分支
git branch -d feature/storage-soc-update

# 删除远端分支
git push origin --delete feature/storage-soc-update
```

PyCharm 里：右下角分支名 → 选择对应分支 → `Delete`。

---

## 8. Commit：记录你做了什么

### Commit 信息格式

```
类型(模块): 简短说明（不超过 50 字）

（可选）详细说明，解释为什么这么改，而不是改了什么
```

| 类型 | 含义 | 示例 |
|------|------|------|
| `feat` | 新增功能 | `feat(storage): add SOC update function` |
| `fix` | 修复 bug | `fix(dispatch): correct merit order sorting` |
| `test` | 新增或修改测试 | `test(storage): add SOC boundary test cases` |
| `refactor` | 重构（不改功能） | `refactor(simulation): extract time loop to separate function` |
| `docs` | 修改文档 | `docs(readme): update installation steps` |
| `style` | 格式调整（不改逻辑） | `style(dispatch): rename var p to load_mw` |

### 好的 Commit vs 坏的 Commit

```bash
# ❌ 看不出做了什么
git commit -m "update"
git commit -m "fix bug"
git commit -m "改了一些东西"

# ✅ 一眼就懂
git commit -m "feat(storage): add SOC update with charge/discharge efficiency"
git commit -m "fix(storage): correct SOC lower bound from 0 to soc_min_mwh"
git commit -m "test(dispatch): add 3-unit merit order hand-calc verification"
```

### 查看提交历史

```bash
# 简洁模式
git log --oneline

# 详细模式
git log

# 图形化（看分支合并情况）
git log --oneline --graph --all
```

---

## 9. Push 与 Pull：和远端同步

### Push（本地 → 远端）

```bash
# 第一次推送新分支（需要指定远端名称）
git push -u origin feature/storage-soc-update

# 之后只需要
git push
```

### Pull（远端 → 本地）

```bash
# 拉取当前分支的远端更新
git pull

# 等价于以下两步的组合
git fetch    # 获取远端最新信息
git merge    # 合并到本地
```

**建议每天早上开始工作前先 pull 一次。**

### Fetch vs Pull 的区别

```
git fetch   只是下载远端最新信息，不改变你本地的代码
git pull    下载 + 自动合并，会修改你的本地代码
```

如果不确定远端改了什么，可以先 `git fetch`，用 `git log` 查看差异，再决定是否 `git pull`。

---

## 10. Pull Request：申请合并代码

Pull Request（PR）是把你的功能分支合并进 `dev` 的正式申请，也是 Code Review 的入口。

### 创建 PR 的步骤

**第一步：把你的分支推送到 GitHub**
```bash
git push origin feature/storage-soc-update
```

**第二步：在 GitHub 上创建 PR**
1. 打开项目的 GitHub 页面
2. 看到黄色提示栏 "Compare & pull request"，点击它
3. 或者进入 `Pull requests` 标签页，点击 `New pull request`
4. 确认：`base: dev` ← `compare: feature/storage-soc-update`

**第三步：填写 PR 说明**

```markdown
## 本次修改目的
实现储能 SOC 更新函数，包含充放电效率和上下限边界处理。

## 修改内容
- src/simulation/storage.py：新增 update_soc() 函数
- tests/test_storage.py：新增 3 个手算验证测试用例

## 对应 Issue
#12

## 测试情况
- [x] 通过单元测试（3 个手算案例全部通过）
- [x] 通过 IEEE 6-bus 3 小时集成测试

## AI 使用情况
- [x] 使用了 AI 生成函数初稿，已逐行核对公式，修改了变量命名和边界处理逻辑

## Reviewer 重点关注
- 第 23 行放电效率的处理方式（除以效率 vs 乘以效率倒数）
```

**第四步：指定 Reviewer**
在右侧 `Reviewers` 栏选择需要审核的队友，然后点击 `Create pull request`。

---

### Code Review 怎么做

**作为 Reviewer：**

1. 打开 PR，点击 `Files changed` 查看代码差异
2. 对有疑问的行点击 `+` 号，写下评论
3. 全部看完后，点击 `Review changes`：
   - `Comment`：只留评论，不表态
   - `Approve`：审核通过
   - `Request changes`：有问题，需要修改

**Review 要检查什么（不只是语法）：**

```
□ 公式是否正确？（充电效率是乘还是除？）
□ 变量名是否有物理含义和单位后缀？
□ 边界条件是否处理完整？（SOC 上下限？）
□ 有没有测试验证？
□ 提交者能解释清楚这段代码吗？
□ AI 生成的部分有没有经过人工核验？
```

**作为 PR 提交者，收到 Review 意见后：**
- 有道理的意见：修改代码，重新提交，回复"已修改，见最新 commit"
- 有疑问的意见：在评论里解释你的思路，讨论清楚再决定是否修改
- 修改完毕后，在 PR 里通知 Reviewer 重新查看

---

## 11. 冲突：遇到了怎么解决

### 为什么会有冲突

两个人同时修改了同一个文件的同一部分，Git 不知道该保留谁的，就会报冲突：

```
小张在 dispatch.py 第 42 行写了：  load_mw = config["load"]
小李在 dispatch.py 第 42 行写了：  load_mw = scenario.load_mw

合并时，Git 不知道用哪个，于是报冲突。
```

### 冲突长什么样

```python
<<<<<<< HEAD（你自己的版本）
    load_mw = config["load"]
=======
    load_mw = scenario.load_mw
>>>>>>> dev（来自 dev 分支的版本）
```

### 解决步骤

**第一步：找到所有冲突文件**
```bash
git status
# 会显示 "both modified: dispatch.py" 这样的信息
```

**第二步：打开冲突文件，手动选择保留内容**

在 PyCharm 中，冲突文件会用红色标记。双击打开后，PyCharm 会提供三栏对比视图：
- 左栏：你的版本
- 右栏：对方的版本
- 中栏：最终结果（你来决定）

点击箭头选择保留哪一方，或者手动在中栏编辑合并后的内容。

**也可以手动编辑文件**，删掉 `<<<<<<<`、`=======`、`>>>>>>>` 这三行标记，保留正确的代码。

**第三步：标记冲突已解决，提交**
```bash
git add dispatch.py
git commit -m "fix: resolve merge conflict in dispatch.py"
```

### 如何减少冲突

```
1. 每天早上 git pull，保持和队友同步
2. 每天把 dev 的最新内容合并进自己的分支
3. 功能模块拆分清楚，减少多人修改同一文件的情况
4. 公共接口一旦约定，不要随意修改
```

---

## 12. 常见问题与急救手册

### 情况一：commit 了不想要的文件

```bash
# 撤销最近一次 commit（保留文件改动，只撤销 commit 记录）
git reset --soft HEAD~1

# 撤销最近一次 commit（同时撤销文件改动，谨慎！）
git reset --hard HEAD~1
```

### 情况二：不小心把错误文件 add 进去了，还没 commit

```bash
# 把某个文件从暂存区移除（文件改动保留）
git restore --staged src/wrong_file.py
```

### 情况三：本地改动一团糟，想回到上次 commit 的状态

```bash
# 丢弃所有未提交的修改（谨慎！不可恢复）
git restore .

# 或者只丢弃某个文件的改动
git restore src/dispatch.py
```

### 情况四：想暂时搁置手头的工作，去处理一个紧急 bug

```bash
# 把当前未提交的改动暂存起来
git stash

# 去处理 bug，提交修复...

# 回来后，恢复之前暂存的内容
git stash pop
```

### 情况五：push 被拒绝了（rejected）

```
! [rejected] feature/storage -> feature/storage (non-fast-forward)
```

这说明远端有你本地没有的提交，需要先拉取：

```bash
git pull
# 如果有冲突，解决冲突后再 push
git push
```

### 情况六：不小心在 main 分支上写了代码（还没 push）

```bash
# 第一步：把当前改动暂存
git stash

# 第二步：切换到正确的功能分支
git checkout feature/my-feature

# 第三步：恢复改动
git stash pop

# 现在改动已经在正确的分支上了，正常 add + commit 即可
```

### 情况七：想查看某次 commit 改了什么

```bash
# 查看最近一次 commit 的详细改动
git show

# 查看指定 commit 的改动（commit 的哈希值从 git log 里复制）
git show a1b2c3d4
```

### 情况八：想知道某行代码是谁写的

```bash
git blame src/simulation/storage.py
```

每行代码前会显示：提交者、提交时间、commit 哈希。

---

## 13. 本项目的 Git 规则速查

### 分支规则

| 规则 | 原因 |
|------|------|
| 不允许直接向 `main` 提交 | main 是稳定版本，随时可运行，不能被未经验证的代码破坏 |
| 不允许直接向 `dev` 提交 | 必须通过 PR + Code Review 才能合并 |
| 每个功能对应一个 feature 分支 | 互不干扰，方便定位问题 |
| 每个任务对应一个 GitHub Issue | 方便追踪进度和讨论 |

### Commit 规则

| 规则 | 原因 |
|------|------|
| Commit 信息必须有意义 | `update` 这种信息在出 bug 时毫无帮助 |
| 不要把一周的代码放进一个 commit | 出问题时无法定位到具体改动 |
| 不要 commit 配置文件里的本地路径 | 会导致队友 pull 后路径报错 |

### 不能上传到 GitHub 的内容

```
❌ 真实电网数据（敏感）
❌ 大型数据文件（>100MB，用 .gitignore 排除）
❌ 包含本地绝对路径的配置文件
❌ Python 虚拟环境目录（venv/、.venv/）
❌ __pycache__/ 和 .pyc 文件
❌ IDE 配置（.idea/、.vscode/）
```

在项目根目录创建 `.gitignore` 文件来自动排除这些内容：

```gitignore
# Python
__pycache__/
*.pyc
*.pyo
.venv/
venv/
*.egg-info/

# PyCharm
.idea/

# 数据文件
data/jilin/
data/east_china/
*.csv.bak

# 系统文件
.DS_Store
Thumbs.db
```

---

## 附：命令速查表

| 操作 | 命令 |
|------|------|
| 克隆仓库 | `git clone <url>` |
| 查看当前状态 | `git status` |
| 查看改了什么 | `git diff` |
| 添加文件到暂存区 | `git add <文件名>` |
| 提交 | `git commit -m "信息"` |
| 推送到远端 | `git push` |
| 拉取远端更新 | `git pull` |
| 查看提交历史 | `git log --oneline` |
| 查看所有分支 | `git branch -a` |
| 创建并切换分支 | `git checkout -b feature/xxx` |
| 切换分支 | `git checkout dev` |
| 合并分支 | `git merge dev` |
| 删除本地分支 | `git branch -d feature/xxx` |
| 暂存当前改动 | `git stash` |
| 恢复暂存的改动 | `git stash pop` |
| 撤销最近 commit | `git reset --soft HEAD~1` |
| 丢弃未提交的改动 | `git restore .` |

---

## 14. PyCharm 中本项目常用 Git 操作命令

本节面向本项目 `TanU_HuBei` 的日常协作。你可以在 PyCharm 底部的 **Terminal** 中直接执行这些命令，也可以使用 PyCharm 的图形界面完成同样操作。

### 14.1 先确认自己当前处于什么状态

每次准备提交、切换分支、拉取代码之前，先执行：

```bash
git status
```

直观理解：

```text
On branch dev
```

表示你当前在 `dev` 分支。

```text
nothing to commit, working tree clean
```

表示当前没有未提交修改，工作区是干净的。

```text
modified: README.md
```

表示 `README.md` 已经被修改，但还没有提交。

```text
Untracked files:
  .idea/
```

表示 Git 发现了新文件或新文件夹，但还没有跟踪。`.idea/` 一般是 PyCharm 本地配置，通常不要提交，应写入 `.gitignore`。

### 14.2 开始一个新任务：从最新 dev 创建自己的分支

适用场景：你准备开始一个新的任务，例如修改 README、写数据读取模块、写储能约束等。

```bash
git switch dev
# 切换到 dev 分支。dev 是团队集成开发分支，新任务一般从 dev 开始。

git pull origin dev
# 从 GitHub 拉取最新 dev，确保你不是基于旧代码开始开发。

git switch -c docs/update-git-guide
# 从当前 dev 创建并切换到一个新分支。
# docs/update-git-guide 是分支名，表示这次任务是更新 Git 指南。
```

如果是代码任务，分支名可以这样写：

```bash
git switch -c feature/hubei-data-loader
# 新建湖北数据读取功能分支。

git switch -c feature/storage-constraints
# 新建储能约束功能分支。

git switch -c fix/power-balance-error
# 新建功率平衡问题修复分支。
```

PyCharm 对应操作：

```text
右上角/右下角分支名 dev
→ New Branch
→ 输入分支名
→ 勾选 Checkout branch
→ Create
```

### 14.3 已经有自己的分支：开始工作前同步 dev

适用场景：你昨天已经创建了 `feature/xxx` 分支，今天继续开发。先让自己的分支跟上团队最新进度。

```bash
git switch dev
# 先回到 dev。

git pull origin dev
# 更新本地 dev，让它和 GitHub 上的 dev 保持一致。

git switch feature/your-task
# 切回你自己的任务分支。把 your-task 替换成真实分支名。

git merge dev
# 把最新 dev 合并进你的任务分支，减少以后合并 PR 时的冲突。
```

如果 `git merge dev` 后出现冲突，不要继续提交。先打开冲突文件，解决冲突，再执行：

```bash
git add 冲突文件名
# 标记冲突已经解决。

git commit -m "fix: resolve merge conflict"
# 提交本次冲突解决记录。
```

### 14.4 查看自己到底改了什么

适用场景：提交前检查修改内容，避免把无关内容提交进去。

```bash
git status
# 查看哪些文件被修改、新增或删除。

git diff
# 查看工作区中尚未 add 的具体改动。

git diff --staged
# 查看已经 add 到暂存区、准备 commit 的具体改动。
```

PyCharm 对应操作：

```text
右键文件
→ Git
→ 显示差异

或按 Ctrl + D 查看当前文件差异。
```

### 14.5 只提交本次任务相关文件

适用场景：你修改了多个文件，但这次只想提交其中一部分。

```bash
git add README.md
# 只把 README.md 放入暂存区。

git add docs/git_guide_for_team.md
# 只把 Git 指南文档放入暂存区。

git add src/data/loader.py
# 只把数据读取模块放入暂存区。

git add src/data/ tests/
# 同时把 src/data/ 和 tests/ 目录下的相关修改放入暂存区。
```

谨慎使用：

```bash
git add .
# 把当前目录下所有修改都放入暂存区。
# 初学阶段不建议随手使用，因为可能把 .idea/、结果文件、临时文件一起加入。
```

PyCharm 对应操作：

```text
Ctrl + K
→ 在提交窗口左侧只勾选本次任务相关文件
→ 不要勾选 .idea/、datasets/、results/、大型日志文件
```

### 14.6 提交到本地仓库

适用场景：你已经确认暂存区内容正确，准备保存为一次本地修改记录。

```bash
git commit -m "docs(git): add pycharm command notes"
# 提交文档修改。

git commit -m "feat(data): add hubei thermal unit loader"
# 提交新增功能：湖北火电机组读取。

git commit -m "fix(storage): correct soc update equation"
# 提交问题修复：修正储能 SOC 更新公式。

git commit -m "test(balance): add power balance hand-check case"
# 提交测试：增加功率平衡手算案例。
```

直观理解：

```text
git add      选择哪些修改进入本次提交
git commit   把选好的修改保存成本地快照
```

PyCharm 对应操作：

```text
Ctrl + K
→ 勾选文件
→ 写 Commit Message
→ 点击 Commit
```

如果你选择 `Commit and Push`，PyCharm 会在本地提交后继续上传到 GitHub。

### 14.7 推送到 GitHub

适用场景：你已经 commit，希望把自己的分支上传到远端，之后才能创建 PR。

第一次推送一个新分支：

```bash
git push -u origin docs/update-git-guide
# 把本地 docs/update-git-guide 分支推送到 GitHub。
# -u 表示建立本地分支和远端分支的对应关系。
# 建立对应关系后，以后在这个分支上可以直接 git push。
```

之后继续推送同一个分支：

```bash
git push
# 把当前分支上新的本地提交继续上传到 GitHub。
```

PyCharm 对应操作：

```text
Ctrl + Shift + K
→ 检查 Push 窗口中的分支名
→ 确认不是 main 或 dev
→ Push
```

### 14.8 创建 Pull Request

适用场景：你的分支已经推送到 GitHub，希望合并进 `dev`。

在 GitHub 页面操作：

```text
Pull requests
→ New pull request
→ base: dev
→ compare: docs/update-git-guide
→ Create pull request
```

含义：

```text
base: dev
```

表示目标分支是 `dev`，也就是你希望把修改合并到哪里。

```text
compare: docs/update-git-guide
```

表示来源分支是你的任务分支，也就是你这次改了什么。

PR 说明建议写清楚：

```markdown
## 本次修改目的
补充 PyCharm 中常用 Git 操作命令，方便新成员按项目规则完成分支、提交、推送和 PR。

## 修改内容
- 在 git_guide_for_team.md 末尾新增 PyCharm 常用 Git 操作命令
- 增加本项目常见场景的命令注释
- 补充误操作恢复命令

## 测试情况
- [x] 已检查 Markdown 结构
- [x] 已确认未上传原始数据、结果文件和 .idea/
```

### 14.9 PR 合并后更新本地 dev

适用场景：你的 PR 已经合并到 GitHub 的 `dev`，本地也要同步。

```bash
git switch dev
# 切回 dev。

git pull origin dev
# 拉取 GitHub 上已经合并的新内容。

git branch -d docs/update-git-guide
# 删除本地已经完成的任务分支。
# -d 只会删除已经合并过的分支，相对安全。
```

如果需要删除远端分支：

```bash
git push origin --delete docs/update-git-guide
# 删除 GitHub 上的远端任务分支。
# 注意：只删除已经合并、不再需要的任务分支。
```

PyCharm 对应操作：

```text
切换到 dev
→ Git Pull
→ 在分支列表中找到已完成分支
→ Delete
```

### 14.10 不想保留本地修改

适用场景：你修改了文件，但后来发现不需要这些修改。

丢弃某个文件的修改：

```bash
git restore README.md
# 丢弃 README.md 的本地修改，恢复到最近一次 commit 的状态。
```

如果文件已经被 add 到暂存区，先取消暂存，再丢弃修改：

```bash
git restore --staged README.md
# 把 README.md 从暂存区拿出来，但保留工作区修改。

git restore README.md
# 丢弃 README.md 的工作区修改。
```

丢弃所有未提交修改：

```bash
git restore .
# 丢弃当前目录下所有已跟踪文件的未提交修改。
# 谨慎使用，执行后这些修改不会进入 Git 历史。
```

清理未跟踪文件或文件夹：

```bash
git clean -fd
# 删除所有未被 Git 跟踪的文件和文件夹。
# 谨慎使用，可能删除新建但尚未提交的代码文件。
```

清理前先预览：

```bash
git clean -fdn
# 只显示会删除什么，不真正删除。
# n 表示 dry-run，适合先检查。
```

### 14.11 改到一半，需要临时切换任务

适用场景：你正在写一个功能，突然要切到另一个分支修复紧急问题，但当前修改还不适合提交。

```bash
git stash
# 临时保存当前未提交修改，让工作区变干净。

git switch fix/urgent-problem
# 切换到另一个分支处理紧急问题。

git stash pop
# 回到原分支后，恢复刚才临时保存的修改。
```

查看暂存记录：

```bash
git stash list
# 查看当前保存了哪些 stash。
```

### 14.12 查看分支和提交历史

适用场景：你想确认当前有哪些分支、提交记录长什么样。

```bash
git branch
# 查看本地分支。带 * 的是当前分支。

git branch -a
# 查看本地分支和远端分支。

git log --oneline
# 用一行显示一个 commit，便于快速查看历史。

git log --oneline --graph --all
# 用图形方式查看所有分支的提交关系。
```

PyCharm 对应操作：

```text
Git
→ Show Git Log

或底部 Git 工具窗口
→ Log
```

### 14.13 本项目最常用的完整流程

文档任务示例：

```bash
git switch dev
# 回到 dev。

git pull origin dev
# 拉取最新 dev。

git switch -c docs/update-git-guide
# 创建文档分支。

git status
# 检查当前状态。

git add docs/git_guide_for_team.md
# 只添加这次修改的 Git 指南文件。

git commit -m "docs(git): add pycharm command notes"
# 本地提交。

git push -u origin docs/update-git-guide
# 推送到 GitHub，然后创建 PR：docs/update-git-guide -> dev。
```

代码任务示例：

```bash
git switch dev
# 回到 dev。

git pull origin dev
# 拉取最新 dev。

git switch -c feature/hubei-data-loader
# 创建数据读取功能分支。

git add src/data/loader.py tests/test_loader.py configs/cases/hubei2030.yaml
# 只添加本次数据读取任务相关文件。
# 不要添加 datasets/hubei2030/ 中的原始数据。

git commit -m "feat(data): add hubei data loader skeleton"
# 本地提交。

git push -u origin feature/hubei-data-loader
# 推送到 GitHub，然后创建 PR：feature/hubei-data-loader -> dev。
```

### 14.14 本项目不要执行的高风险操作

初学阶段，以下命令不要随便执行：

```bash
git push origin main
# 不要直接推送到 main。

git push origin dev
# 不要绕过 PR 直接推送到 dev，除非团队负责人明确要求。

git add .
# 不要在没检查 git status 的情况下直接添加所有文件。

git reset --hard
# 会强制丢弃本地修改，确认无误前不要用。

git clean -fd
# 会删除未跟踪文件，执行前先用 git clean -fdn 预览。
```

提交前的最低检查：

```bash
git status
# 看看有没有 .idea/、datasets/、results/、大型文件被误加入。

git diff --staged
# 看看准备提交的内容是否都属于本次任务。
```

记住本项目的基本原则：

```text
先从 dev 新建自己的任务分支
只提交本次任务相关文件
先 commit 到本地
再 push 到自己的远端分支
最后通过 PR 合并到 dev
main 只保留稳定版本
```

