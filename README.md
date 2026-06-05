# 🎓 CET 智胜 · 英语四六级备考系统

一个基于 Python + CustomTkinter 的本地化四六级备考桌面软件。覆盖词汇、写作、阅读、听力、翻译五大板块,内置近 10 年真题示例数据,提供「2026 AI 押题预测」和「AI 拓展相似练习」功能。

---

## ✨ 功能亮点

### 📚 五大备考板块
| 板块 | 关键特性 |
| ---- | ---- |
| 📝 **词汇** | 真题高频词 1-5 星级划分,支持星级筛选 / 关键词搜索 |
| ✍️ **写作** | 近 10 年真题范文 + **🔮 2026 年 6/12 月押题预测** (含置信度 + 命题依据 + 参考范文) |
| 📖 **阅读** | 近 10 年真题 + **AI 拓展相似练习** (题材/难度/题型自动仿写) |
| 🎧 **听力** | 近 10 年听力原文 + 题目 + **AI 拓展对话/短文** |
| 🗣️ **翻译** | 近 10 年段落翻译 + 参考译文 + **AI 拓展段落** |

### 🤖 AI 模块
- **本地模式 (默认)**:基于近 10 年命题规律的规则引擎,无需联网即可生成拓展题/押题。
- **API 模式 (可选)**:在侧边栏「🔑 配置 API Key」中填入 OpenAI 兼容的 `base_url` + `api_key` + `model`,系统会在生成时优先调用真实大模型,失败时自动回退到本地模式。

### 🎨 现代化界面
- 左侧导航:考试级别 (CET-4/CET-6) + 五大板块
- 右侧内容:大字号标题、卡片化布局、深色/浅色主题一键切换
- 所有 AI 拓展生成的内容自动保存到 SQLite 数据库

---

## 📂 项目结构

```
D:\CET-Prep-System\
├── main.py                       # 入口 (python main.py 启动)
├── requirements.txt              # 依赖列表
├── config.json                   # 用户配置 (主题 / API Key 等)
├── README.md
│
├── core/                         # 业务核心
│   ├── db_init.py                # 数据库初始化 + 示例数据
│   ├── data_manager.py           # 数据访问层 (CRUD)
│   ├── ai_service.py             # AI 押题 / 拓展生成 (本地 + 可选 API)
│   └── theme_manager.py          # 主题管理
│
├── database/
│   └── cet_exam.db               # SQLite (首次运行自动创建)
│
└── ui/                           # 界面层
    ├── app.py                    # 主窗口 (侧边栏 + 内容区)
    ├── components.py             # 复用组件 (星级、卡片、按钮)
    └── views/
        ├── vocabulary.py         # 词汇板块
        ├── writing.py            # 写作板块
        ├── reading.py            # 阅读板块
        ├── listening.py          # 听力板块
        └── translation.py        # 翻译板块
```

---

## 🚀 快速开始

### 1. 安装依赖
```bash
pip install -r requirements.txt
```
(需要 Python 3.10+; 已测试 Python 3.12.10)

### 2. 启动程序
```bash
python main.py
```

> ⚠️ Windows 用户如果遇到中文乱码,请使用 `python -X utf8 main.py`。

首次运行会自动:
1. 在 `database/cet_exam.db` 创建 SQLite 数据库与表结构
2. 写入示例数据:词汇 30 词 / 写作 4 篇 / 阅读 3 篇 / 听力 3 篇 / 翻译 4 篇 / 2026 押题 4 篇

### 3. (可选) 配置 AI
点击侧边栏底部「🔑 配置 API Key」,填入 OpenAI 兼容服务的 `base_url`、`api_key`、`model` 即可启用真实大模型能力。

---

## 🛠️ 数据统计 (已预置)

| 板块 | CET-4 | CET-6 |
| ---- | ---- | ---- |
| 词汇 | 15 词 (含 5★ 高频核心) | 15 词 (含 5★ 高频核心) |
| 写作 | 2 篇真题 | 2 篇真题 |
| 阅读 | 2 篇真题 | 1 篇真题 |
| 听力 | 2 篇真题 | 1 篇真题 |
| 翻译 | 2 篇真题 | 2 篇真题 |
| 2026 押题 | 2 个预测 | 2 个预测 |

如需扩充数据,可在 `core/db_init.py` 的 `*_SEED` 列表里追加,删除 `database/cet_exam.db` 后重新运行 `python -m core.db_init` 即可。

---

## 🧩 扩展提示

- **新增板块**:在 `core/db_init.py` 的 `SCHEMA_SQL` 加表;在 `core/data_manager.py` 加 CRUD;在 `ui/views/` 加视图;在 `ui/app.py` 的 `SECTIONS` 与 `_build_views` 注册即可。
- **替换 AI 引擎**:在 `core/ai_service.py` 的 `generate_*` 方法中加入远程调用,失败时 `return self.fallback()` 即可保留本地兜底。
- **打包为 exe**:推荐 `pyinstaller --noconsole --onefile main.py --name "CET智胜"`。

---

## 📝 License
仅供学习交流使用,真题数据均摘自历年公开真题或改编自样题,如有版权问题请联系作者删除。
