# 金海心语 · Jinhai Xinyu

> 面向大学生的大语言模型心理服务互动平台
> An LLM-powered mental-health support web platform for university students.

[![Python](https://img.shields.io/badge/python-3.9%2B-blue)](https://www.python.org/)
[![Dependencies](https://img.shields.io/badge/dependencies-none-brightgreen)]()
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

**零第三方依赖**：只用 Python 标准库（`wsgiref` + `urllib` + `sqlite3`），不需要 `pip install`，也不需要 Node。

---

## 这个项目解决什么问题

高校心理服务存在三个结构性缺口：**响应滞后**（夜间与假期几乎无覆盖）、**求助门槛高**（污名化顾虑让人不愿走进咨询室）、**服务分散**（科普、测评、倾诉各在一个平台）。

本项目把四件事整合进一个入口，并用"情绪识别 → 策略映射 → 差异化响应"把它们串成闭环，同时把**安全**作为一等设计目标。

## 功能

| 模块 | 说明 |
|---|---|
| **智能对话** | 接入任意兼容 OpenAI 协议的大模型；情绪识别结果驱动响应策略 |
| **情绪测评** | GAD-7 / PHQ-9 标准计分、分级解读、前后测趋势图 |
| **心理科普** | 按学业 / 人际 / 就业 / 情感四类场景组织，支持检索 |
| **心灵树洞** | 匿名发帖、点赞、AI 共情回复、高危内容进人工通道 |

## 快速开始

```bash
python app.py --open
```

浏览器会自动打开 <http://127.0.0.1:8000>。**不配 API Key 也能完整运行**——系统会自动使用内置规则引擎。

> Windows 用户也可以直接双击 `启动.bat`。

## 接入自己的大模型

三种方式任选：

**① 网页里配置**（最简单）— 点右上角状态灯 → 选服务商 → 填 Key → 测试连接 → 保存。

**② 改 `config.json`**

```json
{
  "provider": "deepseek",
  "base_url": "https://api.deepseek.com/v1",
  "model": "deepseek-chat",
  "api_key": "sk-你的key"
}
```

**③ 环境变量** — `JHXY_API_KEY` / `JHXY_BASE_URL` / `JHXY_MODEL`

### 支持的服务商

| 服务商 | `base_url` | 常用模型 |
|---|---|---|
| DeepSeek | `https://api.deepseek.com/v1` | `deepseek-chat` |
| 通义千问 | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `qwen-plus` |
| Kimi | `https://api.moonshot.cn/v1` | `moonshot-v1-8k` |
| 智谱 GLM | `https://open.bigmodel.cn/api/paas/v4` | `glm-4-flash` |
| OpenAI | `https://api.openai.com/v1` | `gpt-4o-mini` |
| 本地 Ollama | `http://127.0.0.1:11434/v1` | `qwen2.5:7b` |

只要兼容 `/chat/completions`，包括自建 vLLM、OneAPI 等均可。

### 验证连通性

```bash
python test_api.py        # 或 python test_api.py --key sk-xxx
```

会直接告诉你失败原因（401 是 key 错、404 是地址错、402 是没钱、解析失败是没网）。

## 架构

```
用户层   浏览器直接访问，无需安装
前端层   原生 HTML / CSS / JS，无构建步骤
服务层   WSGI 应用 → /api/chat  /api/score  /api/report
智能层   对话大模型  +  情绪识别（模型 / 规则双通道）  +  策略映射  +  安全护栏
数据层   SQLite —— 会话 / 对话记录 / 量表结果 / 匿名帖子
```

设计上的关键取舍：**业务能力与模型供应商解耦**。换模型只改配置，上层逻辑不动。

## 安全设计

三道串联护栏：

```
用户输入
   │
   ├─【输入侧】风险识别
   │     命中自杀 / 自伤表达 → 不走模型，直接转介
   │     分流：否定表达、玩笑、第三人称讨论 → 降级为普通情绪，不误报
   │
   ├─ 情绪识别 → 策略映射（安慰疏导 / 陪伴支持 / 人工转接）
   │
   ├─【输出侧】内容过滤
   │     诊断性表述、药物与剂量、自伤方法（双向匹配）、具体手段名词
   │
   └─【兜底】风险轮次若模型未提转介，自动追加
```

代码位置：`core/safety.py`（护栏）、`core/prompts.py`（提示词约束）、`core/emotion.py`（策略映射）。

## 评测结果

`python eval/run_eval.py` 可复现下列数字（离线规则引擎模式）：

| 指标 | 结果 |
|---|---|
| 功能测试（接口级用例） | **65 / 65 通过** |
| 危机输入识别（24 条高风险表述） | 检出率 **95.8%**，精确率 **100%** |
| 危机输入误报（15 条易误判表述） | 误报率 **0%** |
| 越界输出拦截（12 条） | 拦截率 **100%** |
| 正常输出误拦（12 条） | 误拦率 **0%** |
| 量表计分边界用例 | **14 / 14 正确** |
| `/api/chat` 响应（80 次串行） | 平均 **18.6 ms**，P95 **29.3 ms** |
| `/api/score` 响应 | 平均 **11.9 ms**，P95 **18.9 ms** |

情绪四分类（规则通道）准确率 **61.4%**，其中：

| 类别 | 精确率 | 召回率 | F1 |
|---|---|---|---|
| 高风险 | 1.000 | 1.000 | 1.000 |
| 积极 | 1.000 | 0.467 | 0.636 |
| 中性 | 0.390 | 0.941 | 0.552 |
| 消极 | 0.500 | **0.100** | 0.167 |

> **消极类召回仅 0.100，是刻意保留的真实结果。** 失效集中在隐式表达上，例如"投了二十多份简历一个回音都没有"——句中没有任何显式情绪词，基于词典的规则无法捕捉其负面语义。**这正是系统以模型为主通道、规则仅作降级的设计依据。**

> ⚠️ 评测集为自行构造（`eval/testset.py`），规模有限，且与规则库出自同一团队，存在乐观偏差。这些数字是**系统能力指标**，不是临床疗效证据。

## 目录结构

```
.
├── app.py                 服务入口
├── check_env.py           环境自检
├── test_api.py            接口连通性测试
├── config.example.json    配置模板
├── core/
│   ├── config.py          配置加载（兼容带 BOM 的文件）
│   ├── llm.py             大模型客户端（纯 urllib，OpenAI 兼容）
│   ├── prompts.py         提示词工程
│   ├── safety.py          三道安全护栏
│   ├── emotion.py         情绪识别（模型 + 规则双通道）
│   ├── scales.py          GAD-7 / PHQ-9
│   ├── knowledge.py       科普内容
│   ├── fallback.py        离线兜底对话
│   ├── db.py              SQLite 数据层
│   └── wsgi.py            路由 + 静态服务 + API
├── web/                   前端（无构建步骤）
└── eval/                  评测脚本与标注测试集
```

## 接口

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/chat` | 对话，返回回复 / 情绪 / 策略 / 风险标记 |
| POST | `/api/score` | 量表计分 |
| GET | `/api/report?session_id=` | 心理状态小结 |
| GET | `/api/health` | 服务与大模型连通性 |
| GET/POST | `/api/config` | 读取 / 保存接口配置（**仅限本机**） |
| GET | `/api/knowledge` | 科普列表 |
| GET/POST | `/api/tree` | 树洞列表 / 发帖 |
| GET | `/api/assessments?session_id=` | 测评记录与趋势 |

## 为什么不用 Flask

后端是标准 WSGI 应用，可直接由 `gunicorn` / `waitress` 托管。这么做是为了**零依赖部署**——答辩现场、实验室机器常常装不上包。若要迁移到 Flask，只需重写 `core/wsgi.py` 的路由层，业务模块（`emotion` / `scales` / `safety` / `llm`）一行不用改。

## 免责声明

本项目为教学与科研原型，**不提供医学诊断，不替代专业心理咨询**。若你或身边的人正处于危机中，请联系学校心理中心，或拨打心理援助热线。

仓库中的 `eval/testset.py` 含少量人工构造的高危表述样本，仅用于安全机制的离线评测，不来自任何真实用户数据。

## License

[MIT](LICENSE)
