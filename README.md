# Pi-switch

一个为 [pi coding agent](https://pi.dev) 设计的“配置切换”小工具（类似 ccswitch）。
用来快速切换不同的 **模型（model） / API Key / Base URL / 思考等级**，一键写入 pi 的配置文件。

> 运行环境：Windows + Python 3，带 tkinter（Python 官方安装包默认自带的图形库，无需额外安装）。

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
  - 如需生成配置，点「⬇ 全部导入到模型列表」，会把获得到的模型整理成 pi 格式填回表单。
- **模型列表** 填 JSON 数组。示例：
  ```json
  [
    { "id": "deepseek-v4-flash", "name": "DeepSeek V4 Flash", "reasoning": false, "input": ["text"], "contextWindow": 1048576, "maxTokens": 32768 }
  ]
  ```
  若模型列表里只有示例的 `my-model`，激活时会自动忽略，不会写进 pi 配置。
- **思考等级** 可选：`off / minimal / low / medium / high / xhigh / max`，会写成 `defaultThinkingLevel`；留空则不改动 pi 原来的设置。
- **compat** 用于处理某些兼容性开关，例如很多 OpenAI 兼容服务不支持 `developer` 角色或 `reasoning_effort`：
  ```json
  { "supportsDeveloperRole": false, "supportsReasoningEffort": false }
  ```

---

## 备份与恢复

每次「激活」前都会把将要修改的 pi 配置文件备份到本目录的 `backup` 文件夹（带时间戳）。
万一改坏了，用记事本打开备份文件复制回去即可，或在工具里点 **「备份管理」** 打开备份目录。

---

## 常用按钮

| 按钮 | 作用 |
|------|------|
| 新建 | 创建一个新配置 |
| 复制 | 把选中的配置复制一份，可在此基础上修改 |
| 激活 | 把选中的配置应用到 pi（先备份再写入） |
| 删除 | 删除选中的配置 |
| 导入当前 | 读取 pi 当前 `defaultProvider/defaultModel`，导入成配置 |
| 批量导入 | 扫描 `models.json` + `auth.json`，把所有 provider 一次性导入 |
| 备份管理 | 打开备份目录 |
| 打开配置 | 直接打开 pi 的 settings/models/auth/profiles 文件 |

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

生成的可执行文件位于 `dist/` 目录（已被 `.gitignore` 忽略，不随源码上传）。

---

## 常见问题

- **双击 .bat 一闪而过**：说明没找到 Python，或 Python 没加入 PATH。安装时勾选 “Add Python to PATH”。
- **激活后 pi 里看不到模型**：检查模型列表里的 `id` 是否真实存在，`baseUrl` 是否正确。
- **想用环境变量而不是明文 key**：在 API Key 里填 `$环境变量名`。
- **改坏了**：去 `backup` 目录把对应文件恢复。
