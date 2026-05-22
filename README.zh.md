# deepxiv-sdk

**DeepXiv 是一个专为 agent 设计的论文搜索与渐进式阅读工具。**

安装完 `pip` 包即可直接使用，CLI 会在首次调用时自动申请 token 并保存，不需要你先折腾额外配置。

> ### 🚦 服务状态 —— [实时状态页](https://data.rag.ac.cn/status)
>
> - 🟢 **arXiv 检索与阅读** —— 在线。目标是与 arXiv 保持 T+1 同步（受 arXiv 自身约 1 天的 API 延迟影响）。
> - 🔴 **bioRxiv / medRxiv** —— **因服务器原因暂时下线，我们会尽快恢复。** 期间相关命令会返回 `503`。
> - 🔑 找回 token：[data.rag.ac.cn/token-lookup](https://data.rag.ac.cn/token-lookup)（支持 Google 注册，方便没有中国手机号的用户）。
> - ℹ️ 数据处理目前正在尝试更多样的模型，如果发现 TLDR 异常（比如截断的 thinking 内容），欢迎提 issue，我们会修复。

- **🚦 实时状态**: [https://data.rag.ac.cn/status](https://data.rag.ac.cn/status)
- **📚 API 文档**: [https://data.rag.ac.cn/api/docs](https://data.rag.ac.cn/api/docs)
- **🎥 演示视频**: [![Watch Demo](https://img.shields.io/badge/YouTube-Watch%20Demo-red)](https://youtu.be/atr71CbQybM)
- **📄 技术报告**: [![arxiv](https://img.shields.io/badge/arXiv-2603.00084-b31b1b)](https://arxiv.org/abs/2603.00084)
- **📖 English Docs**: [README.md](README.md)

<p align="center">
  <img src="./assets/demo.gif" width="60%">
</p>

> 🚀 **Live Demo**：基于 deepxiv CLI，用 vibe coding 在 1 小时内搭出来的 [DeepResearch demo](https://demo.rag.ac.cn/)，欢迎试用。完整的全栈研究平台也在路上。

---

## DeepXiv 是什么

DeepXiv 围绕 agent 最关键的两类论文工作流构建：

1. **搜索 + 渐进式内容访问** —— 按层读取论文，而不是一上来就读全文。
2. **热点发现 + 热度信号** —— 知道现在什么最值得看。

它的核心思想：agent 应该**先搜、再快速判断、再只精读最值钱的部分**，而不是无脑加载全文。

## 快速开始

```bash
pip install deepxiv-sdk
```

首次使用时，deepxiv 会自动注册一个免费匿名 token（1,000 请求/天），并保存到 `~/.env`：

```bash
deepxiv search "agentic memory" --limit 5
```

如果你想安装完整能力（MCP server + 内置 research agent）：

```bash
pip install "deepxiv-sdk[all]"
```

## 渐进式阅读：搜索 → 判断 → 精读

CLI 是 DeepXiv 的主入口。几个 flag 驱动了「按层读取」，让 agent 不到必要时不加载全文：

```bash
deepxiv search "agentic memory" --limit 5     # 1. 找候选论文
deepxiv paper 2409.05591 --brief              # 2. 判断值不值得继续看
deepxiv paper 2409.05591 --head               # 3. 看结构与 token 分布
deepxiv paper 2409.05591 --section Method     # 4. 只读最值钱的部分
```

- `--brief` —— 标题、TLDR、关键词、引用数、GitHub 链接
- `--head` —— 章节概览与 token 分布
- `--section NAME` —— 只读单个章节（如 `Introduction`、`Method`、`Experiments`）
- `--preview` / `--raw` / *(无 flag)* —— 约 10k 字符预览 / 完整 markdown / 完整论文

---

## CLI 参考

### 搜索论文

基础搜索（默认 arXiv）：

```bash
deepxiv search "transformer" --limit 10
deepxiv search "agentic memory" --limit 20 --format json
```

**按作者 / 机构 / 分类过滤**（逗号分隔）：

```bash
deepxiv search "image generation" \
  --authors "Shitao Xiao,Zheng Liu" \
  --orgs "Beijing Academy of Artificial Intelligence" \
  --categories cs.CV \
  --limit 5
```

> `--authors` 和 `--orgs` 既过滤也参与排序；`--categories` 只过滤，不影响排序。

**按日期和引用数过滤。** `--date-from` / `--date-to` 支持 `YYYY`、`YYYY-MM`、`YYYY-MM-DD`：

```bash
# 2025 年 6 月之后的论文
deepxiv search "image generation" --date-from 2025-06 --limit 5

# 日期下限 + 引用数下限
deepxiv search "diffusion models" --date-from 2024-01 --min-citations 50 --limit 5
```

> ⚠️ 各过滤条件之间是 `AND` 关系。把「精确到某一个月」和「较高的引用数门槛」叠加在
> 一个很具体的 query 上，完全可能合理地返回 **0 条结果** —— 如果搜不到，请放宽日期
> 范围或降低 `--min-citations`。

**高级日期过滤**（`exact` / `after` / `before` / `between`）：

```bash
# exact：精确到月
deepxiv search "image generation" --date-search-type exact --date-str 2025-06 --limit 5

# between：--date-str 传两次（起始、结束）
deepxiv search "image generation" \
  --date-search-type between --date-str 2025-06-01 --date-str 2025-07-01 --limit 5
```

**分页与精排：**

```bash
deepxiv search "LLM alignment" --limit 10 --offset 10        # 第 2 页
deepxiv search "transformer model" --use-fine-rerank --limit 10   # 按需开启精排（默认关闭）
```

JSON 返回体遵循 `{status, total_count, result: [...]}` 结构，详见 [Python SDK](#python-sdk)。

### 读取论文

```bash
deepxiv paper 2409.05591                       # 完整论文
deepxiv paper 2409.05591 --brief               # 快速摘要
deepxiv paper 2409.05591 --head                # 元数据 + 章节
deepxiv paper 2409.05591 --section Introduction
deepxiv paper 2409.05591 --preview             # 约 10k 字符
```

### 热点与热度信号

```bash
deepxiv trending --days 7 --limit 30      # 最近最热的论文（社交信号）
deepxiv paper 2409.05591 --popularity     # 单篇的 views / tweets / likes / replies
```

### Web Search

```bash
deepxiv wsearch "karpathy"
deepxiv wsearch "karpathy" --json
```

每次 `wsearch` 消耗 **20 scores**（其他请求消耗 **1**）。匿名 token 每天有 **1,000 scores**（约 50 次 web search）；[注册 token](https://data.rag.ac.cn/register) 每天有 **10,000 scores**（约 500 次 web search）。

### 基于 Semantic Scholar ID 的元数据读取

```bash
deepxiv sc 258001
deepxiv sc 258001 --json
```

当你的工作流已经持有 Semantic Scholar ID 时很有用。直接返回 Semantic Scholar ID 的**搜索**服务即将推出。

### PMC 生物医学论文

```bash
deepxiv pmc PMC544940 --head
deepxiv pmc PMC544940
```

### bioRxiv & medRxiv 预印本

> 🔴 **暂时不可用。** bioRxiv / medRxiv 服务因服务器原因临时下线，目前会返回
> `503`，我们会尽快恢复 —— 状态见[实时状态页](https://data.rag.ac.cn/status)。
> 以下命令先记录在此，恢复后即可使用。

预印本搜索已并入统一 retrieve 接口，与 arXiv 共享上面的全部过滤参数：

```bash
# 搜索
deepxiv search "protein design" --biorxiv --limit 5
deepxiv search "Alzheimer" --medrxiv --date-from 2024-01

# 通过 DOI 获取单篇论文
deepxiv biorxiv 10.1101/2021.02.26.433129
deepxiv biorxiv 10.1101/2021.02.26.433129 --format text
deepxiv biorxiv 10.1101/2021.02.26.433129 --section Introduction,Methods
deepxiv medrxiv 10.1101/2025.08.11.25333149 --format text

# 也可以在 paper 命令上加 --biorxiv / --medrxiv flag
deepxiv paper 10.1101/2021.02.26.433129 --biorxiv --section Introduction
```

---

## Example Agent Workflows

两个开箱即用的工作流已经写成可复用 skill：

**跟踪近期热点论文** → [skills/deepxiv-trending-digest/SKILL.md](skills/deepxiv-trending-digest/SKILL.md)

```bash
deepxiv trending --days 7 --limit 30 --json
# 然后：逐篇 --brief → 对有希望的跑 --head → 读关键 section → 生成 report
```

**进入一个新研究方向** → [skills/deepxiv-baseline-table/SKILL.md](skills/deepxiv-baseline-table/SKILL.md)

```bash
deepxiv search "agentic memory" --date-from 2026-03-01 --limit 100 --format json
# 然后：批量 brief → 优先保留带 GitHub 的 → --head 定位实验 → 整理成 baseline table
```

---

## Python SDK

```python
from deepxiv_sdk import Reader

reader = Reader()

# 统一 retrieve 接口，默认 arXiv
results = reader.search("agent memory", size=5)
for paper in results["result"]:
    print(paper["arxiv_id"], paper["score"], paper["title"])

# 渐进式阅读
brief = reader.brief("2409.05591")
head = reader.head("2409.05591")
intro = reader.section("2409.05591", "Introduction")

# 其他接口
web = reader.websearch("karpathy")
sc_meta = reader.semantic_scholar("258001")
```

### `reader.search()` 参数

```python
reader.search(
    query,
    size=10,                  # 映射到上游 top_k（1~100）；也可直接传 top_k=
    offset=0,                 # 0~10000
    source="arxiv",           # "arxiv" | "biorxiv" | "medrxiv"
    categories=None,          # list[str]，只过滤
    authors=None,             # list[str]，过滤 + 参与排序
    orgs=None,                # list[str]，过滤 + 参与排序
    min_citation=None,
    date_from=None,           # 便捷参数；"YYYY" / "YYYY-MM" / "YYYY-MM-DD"
    date_to=None,
    date_search_type=None,    # 高级：between / exact / after / before
    date_str=None,            # 高级：str 或 [start, end]
    use_fine_rerank=False,    # SDK 默认关闭（更便宜）；需要更好排序时设为 True
)
```

返回结构：

```jsonc
{
  "status": "success",
  "total_count": 3,
  "result": [
    {
      "arxiv_id": "2506.18871",    // source 为 biorxiv/medrxiv 时对应字段名变化
      "title": "...", "score": 0.9475, "abstract": "...", "tldr": "...",
      "authors": [{ "name": "...", "orgs": ["..."] }],
      "url": "...", "date": "2025-06-23T17:38:54Z",
      "citation_count": 217, "categories": ["cs.CV"]
    }
  ]
}
```

### Reader 方法

```python
reader.brief(arxiv_id)             # 标题、TLDR、关键词、引用数、GitHub 链接
reader.head(arxiv_id)              # 元数据 + 章节概览
reader.section(arxiv_id, name)     # 单个章节
reader.preview(arxiv_id)           # 约 10k 字符预览
reader.raw(arxiv_id)               # 完整 markdown
reader.json(arxiv_id)              # 结构化 JSON
reader.websearch(query)            # web 搜索（消耗 20 scores）
reader.semantic_scholar(sc_id)     # 通过 Semantic Scholar ID 查元数据
reader.trending(days=7, limit=30)  # 热点论文
reader.social_impact(arxiv_id)     # 热度指标
reader.pmc_head(pmc_id)            # PMC 元数据
reader.pmc_json(pmc_id)            # 完整 PMC JSON
```

> 🔴 bioRxiv / medRxiv 相关接口 —— `reader.search(source="biorxiv"|"medrxiv")`、
> `reader.biomed_data(...)`、`reader.biomed_search(...)` —— **因服务器原因暂时下线**，
> 详见上方服务状态。

<details>
<summary><b>Search API 变更（2026-04）</b> —— 从旧的 Elasticsearch 风格接口迁移说明</summary>

搜索后端已迁移到统一的 `/arxiv/?type=retrieve`，SDK 尽量保持参数名：

| 参数 | 状态 | 说明 |
|---|---|---|
| `size` | 保留 | 映射到上游 `top_k`，也支持直接传 `top_k=`。 |
| `offset` | 保留 | 上限 `0~10000`。 |
| `categories` / `authors` / `min_citation` | 保留 | 语义未变。 |
| `source` | 新增 | `"arxiv"`（默认）/ `"biorxiv"` / `"medrxiv"`。`reader.biomed_search()` 现在只是薄包装。 |
| `orgs` | 新增 | 机构过滤，同时参与排序。 |
| `date_search_type` / `date_str` | 新增 | `between` / `exact` / `after` / `before`。 |
| `date_from` / `date_to` | 保留（自动映射） | 自动转成 `date_search_type` + `date_str`；现在也支持 `YYYY` / `YYYY-MM`。 |
| `use_fine_rerank` | 新增 | 上游默认 `True`，**SDK 默认 `False`**。 |
| `search_mode` / `bm25_weight` / `vector_weight` | **已废弃** | 仍可传，但会被忽略（打印 warning）。 |
| `search_funcs` / `return_contents` / `return_roc` | 不暴露 | 始终用默认值。需要正文请用 `reader.raw()` / `section()` / `json()`。 |

返回结构迁移：`{total, took, results}` → `{status, total_count, result}`；每条结果 ID 字段随 `source` 变为 `arxiv_id` / `biorxiv_id` / `medrxiv_id`；`paper["citation"]` → `paper["citation_count"]`。CLI 侧：`--limit` 映射到 `size`，`--mode` 已废弃为 no-op，`--biorxiv` / `--medrxiv` 切换数据源。
</details>

---

## Agent 集成

DeepXiv 设计上就适合接入 Codex、Claude Code、OpenClaw 以及类似的 agent runtime。

### MCP Server

添加到 Claude Desktop MCP 配置文件：

- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
- **Linux**: `~/.config/Claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "deepxiv": {
      "command": "deepxiv",
      "args": ["serve"],
      "env": { "DEEPXIV_TOKEN": "your_token_here" }
    }
  }
}
```

MCP 可用工具：

| 工具 | 说明 |
|------|------|
| `search_papers` | 搜索 arXiv 论文 |
| `get_paper_brief` | 快速摘要 |
| `get_paper_metadata` | 完整元数据 |
| `get_paper_section` | 读取特定章节 |
| `get_full_paper` | 完整论文 |
| `get_paper_preview` | 论文预览 |
| `get_pmc_metadata` | PMC 论文元数据 |
| `get_pmc_full` | 完整 PMC 论文 |

### CLI Skill

```bash
mkdir -p $CODEX_HOME/skills
ln -s "$(pwd)/skills/deepxiv-cli" $CODEX_HOME/skills/deepxiv-cli
```

对于不支持原生 skill 的框架，可以直接把 [skills/deepxiv-cli/SKILL.md](skills/deepxiv-cli/SKILL.md) 当作操作指令加载。

### 内置 Research Agent

如果你不想自己拼工作流，CLI 里已经内置了一个 ReAct agent（用 `pip install "deepxiv-sdk[all]"` 安装）。它支持任何 OpenAI 兼容 API（OpenAI、DeepSeek、OpenRouter、本地 Ollama 等），可以多轮地搜索 → 阅读 → 推理。

```bash
deepxiv agent config   # 配置 LLM API（只存在本地）
deepxiv agent query "What are the latest papers about agent memory?" --verbose
```

```python
from deepxiv_sdk import Agent

agent = Agent(api_key="your_key", base_url="https://api.deepseek.com/v1", model="deepseek-chat")
print(agent.query("比较 transformer 和 attention mechanism 的关键想法"))
```

---

## Token 管理

deepxiv 按以下顺序解析 token：`--token` 选项 → `DEEPXIV_TOKEN` 环境变量 → `~/.env`。首次使用时会自动注册一个。

```bash
deepxiv search "agent"                          # 首次使用自动注册（推荐）
deepxiv config --token YOUR_TOKEN               # 保存到 ~/.env
export DEEPXIV_TOKEN="your_token"               # 或用环境变量
deepxiv paper 2409.05591 --token YOUR_TOKEN     # 或每条命令单独传
```

| Token 类型 | 日限额 | 如何获取 |
|---|---|---|
| 自动注册（匿名） | 1,000 请求 | 首次使用 CLI 时自动完成 |
| 注册 token | 10,000 请求 | [data.rag.ac.cn/register](https://data.rag.ac.cn/register) |
| 自定义 / 更高 | 联系我们 | 邮件 `tommy[at]chien.io` 说明用途 |

**免费测试论文**（无需 token）—— arXiv：`2409.05591`、`2504.21776`；PMC：`PMC544940`、`PMC514704`。

## 错误处理

```python
from deepxiv_sdk import (
    Reader,
    AuthenticationError,  # 401 - 无效或过期的 token
    RateLimitError,       # 429 - 达到日限额
    NotFoundError,        # 404 - 论文未找到
    ServerError,          # 5xx - 服务器错误
    APIError,             # 其他 API 错误
)

try:
    paper = reader.brief("2409.05591")
except AuthenticationError:
    print("请更新你的 token")
except RateLimitError:
    print("已达到日限额")
except NotFoundError:
    print("论文未找到")
except APIError as e:
    print(f"API 错误: {e}")
```

## 常见问题

- **我需要 token 才能用吗？** 不一定 —— 部分论文免费，且首次使用会自动注册。
- **搜索最多返回多少？** 每次 100 条；用 `--offset` / `offset=` 分页。
- **搜索返回 0 条结果？** 放宽过滤条件 —— `--date-*` 与 `--min-citations` 叠加会把结果集卡得太窄。
- **怎么处理超时？** Reader 默认自动重试（最多 3 次，指数退避）。可自定义：`Reader(timeout=120, max_retries=5)`。
- **可以缓存内容吗？** 可以 —— 取到后本地缓存即可，论文内容不会变。
- **agent 支持哪些模型？** 任何 OpenAI 兼容 API（OpenAI、DeepSeek、OpenRouter、本地 Ollama 等）。
- **bioRxiv / medRxiv 返回 `503`？** 已知故障 —— 见[状态页](https://data.rag.ac.cn/status)。

## 示例

查看 [examples/](examples/)：`quickstart.py`、`example_reader.py`、`example_agent.py`、`example_advanced.py`、`example_error_handling.py`。

## Roadmap & 覆盖范围

DeepXiv 的目标是逐步成为一个**亿级（100M+）的 academic paper data interface**，并越来越多地以 Semantic Scholar metadata 作为基础元数据层：

1. arXiv 全量覆盖 + T+1 自动更新
2. anyXiv 覆盖（bioRxiv、medRxiv 等）
3. 全量开放获取（OA）文献覆盖

| 数据源 | 状态 |
|---|---|
| arXiv | ✅ 在线 —— 当前主要数据源 |
| PubMed Central (PMC) | ✅ 在线 —— 生物医学与生命科学 |
| bioRxiv / medRxiv | 🔴 因服务器原因暂时下线，会尽快恢复 |
| Semantic Scholar 元数据 | 🔄 作为基础元数据层持续扩展 |

> DeepXiv 专注于开放获取文献，让 agent 能基于可直接访问的论文数据工作，而不是被订阅墙卡住。

## 许可证 & 支持

MIT License，见 [LICENSE](LICENSE)。

- 🚦 **状态**: [data.rag.ac.cn/status](https://data.rag.ac.cn/status)
- 🐛 **GitHub Issues**: [github.com/qhjqhj00/deepxiv_sdk/issues](https://github.com/qhjqhj00/deepxiv_sdk/issues)
- 📚 **API 文档**: [data.rag.ac.cn/api/docs](https://data.rag.ac.cn/api/docs)
- 📧 **更高限额**: [注册](https://data.rag.ac.cn/register) 获得 10,000 请求/天，或邮件 `tommy[at]chien.io` 说明用途申请自定义限额
</content>
