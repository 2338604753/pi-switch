# Pi-switch

一个为 [pi coding agent](https://pi.dev) 设计的“配置切换”小工具（类似 ccswitch）。
用来快速切换不同的 **模型（model） / API Key / Base URL / 思考等级**，一键写入 pi 的配置文件。

> 运行环境：Windows + Python 3，带 tkinter（Python 官方安装包默认自带的图形库，无需额外安装）。

---

## 下载 / 安装

**方式一：直接用免安装版（推荐）**

前往 GitHub Releases 下载，解压后双击 `Pi-switch.exe` 即可运行，无需安装 Python：

- 最新版本：<https://github.com/2338604753/pi-switch/releases>
- 直接下载：<https://github.com/2338604753/pi-switch/releases/download/v1.1.0/Pi-switch.exe>

**方式二：从源码运行**

需要 Python 3（带 tkinter，官方安装包默认自带）：

```bash
python pi_switch.py
```

或直接双击 `启动Pi-switch.bat` / `启动Pi-switch.pyw`。

---

## 有什么作用

你每次手动改 `~/.pi/agent` 下的配置很麻烦，这个工具把常用的配置做成一个个 **profile（配置文件）**，
点一下「激活」，就会自动备份并写入 pi 真正读取的文件：

| pi 配置文件 | 作用 |
|-------------|------|
| `~/.pi/agent/settings.json` | `defaultProvider` / `defaultModel` / `defaultThinkingLevel`（启动时用的 Provider、模型、思考等级） |
| `~/.pi/agent/models.json` | 自定义 provider（`baseUrl` / `api` / `apiKey` / `compat` / `models`） |
| `~/.pi/agent/auth.json` | 内置 provider 的 API key（如 openai、anthropic、opencode 等） |

激活后，下次启动 pi（或打开 `/model` 选择）即生效。

---

## 怎么用

1. 双击 **`启动Pi-switch.bat`**（或命令行运行 `python pi_switch.py`）。
2. **左侧**是配置文件列表。可以用「新建」创建，或先用「批量导入」把已存在的 provider 全部导进来。
3. **右侧**表单里填写/修改：
   - 名称、Provider ID
   - 类型：**自定义 provider**（写 `models.json`）或 **内置 provider**（写 `auth.json`）
   - Base URL、API 类型、API Key、默认模型、思考等级
   - 模型列表（JSON）、兼容设置 compat（JSON）
4. 点 **「保存配置」** 存到本地，或点 **「激活并应用」** 直接写入 pi 配置。

---

## 几个关键点

- **API Key** 支持直接填明文，也可以用 pi 支持的语法：`$ENV_VAR`（读取环境变量）或 `!command`（执行命令取 stdout）。
  - 例如 `apiKey` 填 `$MY_API_KEY`，pi 会在请求时解析成环境变量的值。
- **获取模型**：在表单填好 **Base URL** 和 **API Key**，点「⚙ 获取模型」，会自动调用 `{baseUrl}/models` 拉取该接口下的所有模型并列出。每个模型旁边有：
  - **复制**：一键复制模型名（ID）。
  - **测试**：向该模型发一个最简请求，验证它是否能正常响应（2xx 即算通）。
  - 顶部有 **☑ 标记为推理模型(reasoning)** 勾选框（默认勾上），决定导入时模型的 `reasoning` 写 `true` 还是 `false`。
    如果你的接口里有非推理模型，取消勾选后导入，再手动改对应模型即可。
  - 如需生成配置，点「⬇ 全部导入到模型列表」，会把获得到的模型整理成 pi 格式填回表单。
- **模型列表** 填 JSON 数组。示例：
  ```json
  [
    { "id": "deepseek-v4-flash", "name": "DeepSeek V4 Flash", "reasoning": true, "input": ["text"], "contextWindow": 1048576, "maxTokens": 32768 }
  ]
  ```
  > ⚠️ **`reasoning` 必须是 `true`，思考才会生效。**
  > pi 内部只有在 `model.reasoning === true` 时才会发送思考参数（`reasoning_effort`），
  > 也才会把接口返回的 `reasoning_content` 渲染成思考块。填 `false` 的话，
  > 即使把「思考等级」选成 `high`，pi 也不会有任何思考输出。
  > 非推理模型（如纯对话模型）保持 `false` 即可。

  若模型列表里只有示例的 `my-model`，激活时会自动忽略，不会写进 pi 配置。
- **思考等级** 可选：`off / minimal / low / medium / high / xhigh / max`，会写成 `defaultThinkingLevel`；留空则不改动 pi 原来的设置。

  > 🔄 **会自动联动**：只要填了非 `off` 的思考等级，点「保存配置 / 激活并应用」时就会自动：
  > - 把模型列表里每个模型的 `reasoning` 置为 `true`；
  > - 把 `compat.supportsReasoningEffort` 置为 `true`；
  > - 若 `compat` 里没有 `supportsDeveloperRole`，补上 `false`；
  > - 选了 `xhigh` / `max` 时，给每个模型补上 `thinkingLevelMap`（见下）。
  >
  > 改动结果会在状态栏提示，并同步回填到表单，不会再出现「界面显示 false」的情况。
  > 选 `off` 时刻意**不会**把 `reasoning` 改回 `false`，也不会删除你已有的档位映射，
  > 避免把你显式配好的模型改坏。

  > ⚠️ **为什么 `xhigh` / `max` 必须配 `thinkingLevelMap`**：
  > 在 pi 里，`xhigh` 和 `max` 属于 **opt-in 的扩展档位**：模型必须用 `thinkingLevelMap`
  > 显式声明支持，否则 pi 的 `clampThinkingLevel()` 会把它悄悄压低成 `high`
  > （见 pi 文档 `docs/models.md` → “Thinking Level Map”）。
  > 也就是说**只写 `defaultThinkingLevel: "max"` 是没用的**，状态栏会一直显示 `high`。
  > 从 v1.1.1 起本工具会自动帮你补上，选 `xhigh` 时写：
  > ```json
  > "thinkingLevelMap": { "xhigh": "xhigh" }
  > ```
  > 选 `max` 时写（连 `xhigh` 一起放开，档位连续，降档不用再改配置）：
  > ```json
  > "thinkingLevelMap": { "xhigh": "xhigh", "max": "max" }
  > ```
  > 已经手写过映射的模型不会被覆盖（只有缺失或显式为 `null` 的项才会被补上），
  > 也可以用 `null` 显式屏蔽某一档，例如 `{ "xhigh": null, "max": "max" }`。
- **compat** 用于处理某些兼容性开关，例如很多 OpenAI 兼容服务不支持 `developer` 角色：
  ```json
  { "supportsDeveloperRole": false, "supportsReasoningEffort": true }
  ```
  - `supportsDeveloperRole`：置 `false` 时 pi 用 `system` 角色而非 `developer` 角色发送系统提示词。
    多数第三方 OpenAI 兼容中转不认 `developer`，会直接返回 400，所以推荐 `false`。
  - `supportsReasoningEffort`：该接口是否支持 `reasoning_effort` 参数。
    因为 pi 只在 `model.reasoning === true` 时才发送它，所以填 `true` 是安全的。
  > 一般用**不需要**加 `thinkingFormat`。pi 的 `openai-completions` 会自动识别
  > `reasoning_content` / `reasoning` / `reasoning_text` 字段，`thinkingFormat`
  > 只影响“发送什么参数”，不设置反而兼容面更广。

---

## 备份与恢复

每次「激活」前都会把将要修改的 pi 配置文件备份到本目录的 `backup` 文件夹（带时间戳）。
万一改坏了，用记事本打开备份文件复制回去即可，或在工具里点 **「备份管理」** 打开备份目录。

---

## 常用按钮

| 按钮 | 作用 |
|------|------|
| 保存配置 (Save) | 保存当前编辑内容到 `profiles.json`（不弹窗，结果看状态栏） |
| 激活并应用 (Activate) | 先保存，再把配置写入 pi 的 `models.json` / `auth.json` / `settings.json`（不弹窗，结果看状态栏） |
| 新建 | 创建一个新配置 |
| 复制 | 把选中的配置复制一份，可在此基础上修改 |
| 激活 | 把选中的配置应用到 pi（先备份再写入，同样不弹确认框） |
| 删除 | 删除选中的配置 |
| 导入当前 | 读取 pi 当前 `defaultProvider/defaultModel`，导入成配置 |
| 批量导入 | 扫描 `models.json` + `auth.json`，把所有 provider 一次性导入 |
| 备份管理 | 打开备份目录 |
| 打开配置 | 直接打开 pi 的 settings/models/auth/profiles 文件 |
| ↻ 刷新当前配置 | 重新从磁盘读取 `profiles.json` 与 pi 配置，刷新列表并重填右侧表单 |

---

## 配置文件位置说明

本工具的配置保存在 **`profiles.json`**（与 `pi_switch.py` 同目录），与 pi 自身配置互不干扰。

- 本工具写配置文件：`~/.pi/agent/`
- 本工具本地配置：`./profiles.json`
- 备份目录：`./backup/`

> **示例文件**：仓库中提供了 `profiles.example.json`，里面是**脱敏后的占位示例**（Key 为 `sk-REPLACE_WITH_YOUR_KEY`），方便了解格式。你可以把它复制成 `profiles.json` 再改成自己的配置。

---

## ⚠️ 安全提示（重要）

- **`profiles.json` 会保存真实 API Key（明文）**，请**不要**把它提交到公开仓库！
- 本仓库的 `.gitignore` 已默认忽略 `profiles.json`、`backup/`、`dist/`、`build/` 等文件。
- 如果意外把 Key 暴露了，请尽快到对应服务商**重置/轮换**该 Key。
- 更安全的做法：在「API Key」里填 `$环境变量名`（如 `$MY_API_KEY`），让 pi 在运行时读取环境变量，避免明文落盘。
- 打包成 exe 时，`profiles.json` 并**不会**被打进 exe 里，它始终是运行目录下独立存在的文件。

---

## 项目结构

```
Pi-switch/
├── pi_switch.py           # 主程序（tkinter 图形界面）
├── 启动Pi-switch.bat        # 双击启动脚本（无窗口/有窗口自适应）
├── 启动Pi-switch.pyw        # 无窗口启动器（双击运行）
├── Pi-switch.spec          # PyInstaller 打包配置
├── app.ico                 # 程序图标
├── profiles.example.json   # 脱敏示例配置（复制为 profiles.json 使用）
├── .gitignore              # 忽略构建产物与含敏感信息的运行文件
└── README.md
```

---

## 打包成 exe（可选）

需要 [PyInstaller](https://pyinstaller.org/)：

```bash
pip install pyinstaller
pyinstaller Pi-switch.spec
```

`Pi-switch.spec` 配置的是 **单文件 exe**（onefile），生成的可执行文件为：

```
dist/Pi-switch.exe
```

`dist/` 与 `build/` 已被 `.gitignore` 忽略，不随源码上传。
因为 `profiles.json` 是运行目录下的独立文件，单文件 exe 不会被它打进去，可放心分发。

---

## 常见问题

- **双击 .bat 一闪而过**：说明没找到 Python，或 Python 没加入 PATH。安装时勾选 “Add Python to PATH”。
- **在界面里把「思考等级」选成 high，但 compat 里 `supportsReasoningEffort` 还是 false**：
  这是 v1.0.0 的 bug（已修）。v1.1.0 起保存/激活时会自动联动，并在状态栏提示改了什么。
- **思考等级选了 `xhigh` / `max`，pi 状态栏却一直显示 `high`**：
  这是 v1.1.0 及更早版本的 bug（v1.1.1 已修）。原因是旧版只写了 `defaultThinkingLevel`，
  没给模型写 pi 要求的 `thinkingLevelMap`，于是 `xhigh` / `max` 被 `clampThinkingLevel()` 压回 `high`。
  v1.1.1 起保存/激活会自动补上映射；如果你手上是旧版，也可以手动在「模型列表 (JSON)」里给模型加：
  ```json
  "thinkingLevelMap": { "xhigh": "xhigh", "max": "max" }
  ```
  然后「保存配置」→「激活并应用」，**重启 pi**，再在 `/thinking` 里选一次档位即可（会话内已有档位要重新选）。
- **在外部改了 `profiles.json`，点「刷新当前配置」没反应**：
  这也是 v1.0.0 的 bug（已修）：旧版该按钮只刷新顶部状态文字，不重载表单。v1.1.0 起会真正重新读取并重填表单。
- **激活后 pi 里看不到模型**：检查模型列表里的 `id` 是否真实存在，`baseUrl` 是否正确。
- **pi 里没有思考输出**：确认模型的 `reasoning` 是 `true`，且「思考等级」不是 `off`；
  另外若接口类型是 `openai-responses`，部分中转在带系统提示词或结构化 input 时会丢掉思考内容，
  这种情况改用 `openai-completions` 即可。
- **想用环境变量而不是明文 key**：在 API Key 里填 `$环境变量名`。
- **改坏了**：去 `backup` 目录把对应文件恢复。

---

## 更新日志

### v1.1.1

修复 `xhigh` / `max` 选了不生效，以及「保存 / 激活」弹窗过多：

- **修复 `xhigh` / `max` 被压回 `high`**：pi 里这两个是 opt-in 的扩展档位，必须由模型级
  `thinkingLevelMap` 显式声明；旧版只写 `defaultThinkingLevel`，所以永远被 clamp 成 `high`。
  现在保存/激活时会自动补 `thinkingLevelMap`（选 `max` 就连 `xhigh` 一起放开），
  只补缺失或 `null` 的项，绝不覆盖手写值，选 `off` 也不反向修改。
- **左侧「激活」按钮也会跑一遍联动**：以前它直接用 profile 里的旧内容写入，
  老的、没带 `thinkingLevelMap` 的配置激活后依然不生效；现在激活前也会同步一次。
- **「保存配置」/「激活并应用」不再弹窗**：成功结果改为显示在底部状态栏
  （`已保存配置：xxx` / `已激活：xxx`），少点一次「确定」。
  仅保留真正出错或防误操作的提示：JSON 格式错误、Provider ID 为空、Base URL 不合法、
  激活失败、新建配置时 ID 重名覆盖确认。
- **「思考等级」旁的说明文字**更新为：非 `off` 会自动补 `reasoning=true`，`xhigh`/`max` 会自动补 `thinkingLevelMap`。

### v1.1.0

修复「思考等级」不生效、刷新不重载、导入模型强制 `reasoning=false`：

- **`⚙ 获取模型` 导入不再强制 `reasoning: false`**：新增「标记为推理模型(reasoning)」勾选框，默认 `true`。
- **`MODEL_TEMPLATE` 默认 `reasoning: true`**。
- **思考等级自动联动**：填了非 `off` 的思考等级时，保存/激活会自动把模型 `reasoning`
  与 `compat.supportsReasoningEffort` 置为 `true`，并提示 + 回填表单；选 `off` 时不反向修改。
- **`↻ 刷新当前配置` 真正重载**：重新读取 `profiles.json` + pi 配置，刷新列表、状态与右侧表单。
- **表单如实显示**：空数组/空对象原样显示成 `[]` / `{}`，不再用模板冒充导致界面与磁盘不一致。
- **`COMPAT_TEMPLATE` 改为推荐默认值** `{"supportsDeveloperRole": false, "supportsReasoningEffort": true}`。
- **`导入当前` / `批量导入` 现在会一起导入 `defaultThinkingLevel`**（旧版漏了，导致思考等级显示为空、联动失效）。
- **`Pi-switch.spec` 改为单文件打包**，与 README 里的 `Pi-switch.exe` 下载保持一致。

### v1.0.0

- 首个版本：profile 管理 / 一键激活 / 获取模型 / 备份管理。
