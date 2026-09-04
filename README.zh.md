# DeepXiv 1.0 —— 补上 agentic search 缺失的那层数据

Agent 会推理，缺的是可供推理的底料：论文全文、真实引用、以及一个不会只丢回十条蓝链接的检索循环。DeepXiv 就是这一层 —— 提一个问题，拿到一个有据可查的答案。

```bash
pip install deepxiv-sdk
```

> **Beta：** `deepxiv talent`（学者检索与人才画像）还没上 PyPI。功能在 `1.1.0b1` 里，
> 人才库数据仍在建设中，暂时用源码安装：
>
> ```bash
> pip install git+https://github.com/DeepXiv/deepxiv_sdk.git
> ```


- **🌐 正式系统**: [deepxiv.com](https://deepxiv.com) —— 基于 deepxiv-sdk 构建的官方研究平台
- **📚 API 文档**: [data.rag.ac.cn/api/docs](https://data.rag.ac.cn/api/docs)
- **🚦 实时状态**: [data.rag.ac.cn/status](https://data.rag.ac.cn/status)
- **📄 技术报告**: [![arxiv](https://img.shields.io/badge/arXiv-2603.00084-b31b1b)](https://arxiv.org/abs/2603.00084)
- **📖 English Docs**: [README.md](README.md)

<p align="center">
  <img src="./assets/demo.gif" width="100%">
  <br>
  <em><code>deepxiv ask</code> —— 一个问题进去，一个带引用的答案流式出来</em>
</p>

---

## 1.0 新功能：Agentic Search

两个同构的接口。一个问题进去，服务端自主调工具、按需读原文，流式返回一个带引用的答案。

```bash
deepxiv ask "what speedup does speculative decoding report on HumanEval"
deepxiv ask "Anthropic Claude API 的定价档位" --web
```

| | 数据源 | 引用形式 | 适合 |
|---|---|---|---|
| **`deepxiv ask`** | 本地全文 arXiv 库（Qdrant 混合检索 + 论文正文） | `[arXiv:2512.15176]` 真实 ID | 论文里的方法、数字、实验结果 |
| **`deepxiv ask --web`** | Google + 已缓存网页正文 | 指向真实 URL 的 markdown 链接 | 时效信息、产品、定价、非学术内容 |

两个都不是网页搜索框的包装：arXiv 侧真的会读论文章节，web 侧真的会读缓存下来的网页正文。

### ⚠️ 仅限注册用户

Agentic search 需要在 **[data.rag.ac.cn/register](https://data.rag.ac.cn/register)** 注册获得的 key。SDK 首次使用时自动注册的 token **不可用**，会返回 `403`。

**目前所有账号都有每天 300 次的免费额度**（与 `deepxiv talent` 共用）。这份额度与账号的通用 daily limit 相互独立 —— 普通搜索和论文阅读不受它影响，反之亦然。需要更高额度请邮件联系 `tommy[at]chien.io` 说明用途。

```bash
deepxiv config --token YOUR_REGISTERED_KEY
```

### 答案长什么样

```
$ deepxiv ask "what speedup does DEER report on HumanEval"

DEER reports a 5.54× speedup on HumanEval (with Qwen3-30B-A3B as the target
model), compared to EAGLE-3's 2.41× on the same benchmark [arXiv:2512.15176].

📚 Sources (1 cited, 10 retrieved — use --all-sources for the rest):
  1. [2512.15176] DEER: Draft with Diffusion, Verify with Autoregressive Models
     https://arxiv.org/abs/2512.15176
```

答案走 **stdout**，来源和进度走 **stderr** —— 所以 `deepxiv ask "…" > answer.md` 拿到的是干净的答案。

### effort 档位

| `--effort` | 取证轮数 | 首字（arXiv） | 首字（web） |
|---|---|---|---|
| `default`（默认） | 1–2 | **3–4s** | 5–9s |
| `high` | 3 | 7–8s | ≈13s |
| `xhigh` | 4–5 | 9–13s | 更久 |

轮数是上限不是下限，证据够了会提前收敛。web 更慢是因为 Google 搜索 cache miss 要 1.7–4.3s 且不可控。

### 怎么写 query

这比任何 flag 都重要。

- **越具体越好。** 这个服务假设 query 已经 refine 过。`"what compression ratio does KV cache eviction report on LongBench"` 的效果远好于 `"kv cache"`。
- **想要具体数字就在 query 里说。** "what speedup" / "which benchmark" 这类措辞会让模型去读原文，而不是只看摘要和 snippet。
- **中文 query 直接用。** arXiv 侧会改写成英文技术术语再检索（底层索引是英文的），web 侧会自动切到中文 locale。答案默认用 query 的语言回。
- **arXiv 的范围限定写进 query 即可** —— 年份、会议（NeurIPS/ICLR/CVPR）、分类（cs.CL）、作者、机构、最小引用数，模型会转成检索过滤条件。
- **结果不理想时换措辞重试。** 调高 `--effort` 只增加读原文的轮数，改变不了首轮召回的方向。

### 参数

```bash
deepxiv ask "reward hacking in RLHF" --verbose          # stderr 显示工具调用与配额
deepxiv ask "state space models vs transformers" --json # 输出单个 JSON
deepxiv ask "MoE routing collapse" --no-stream          # 等完整答案再输出
deepxiv ask "diffusion samplers" --all-sources          # 列出全部召回来源

deepxiv ask "NeurIPS 2025 最佳论文" --web --search-type news
deepxiv ask "检索评测方法学" --web --search-type scholar
```

`--top-k N`（1–30，仅 arXiv）控制首轮检索条数。`--search-type` / `--gl` / `--hl` 仅 web 可用。`--max-answer-tokens N`（256–16384）限制答案长度，`--language LANG` 指定答案语言。

### 关于结果的三件事

> **引用是真的。** prompt 明确禁止编造 arXiv ID 或 URL，库里没有相关论文时会直说"没有"，而不是编一个。`[arXiv:2512.15176]` 可直接拼成 `https://arxiv.org/abs/2512.15176`。

> **sources 是召回集，不是引用列表。** 召回 10 篇最后只支撑 1 条引用是常态。CLI 默认只列被引用的，`--all-sources` 看全部。

> **web 的证据强度分两档。** 服务端只读**已缓存**的网页正文，不做实时抓取，所以没缓存的页面只贡献了一条 snippet。中文站点和新闻页的缓存覆盖率偏低。CLI 会区分标注"读过正文"（📄）和"仅摘要"（🔗），答案里也会标明哪些结论只来自搜索摘要。请据此打折。

另外：答案撞到 `--max-answer-tokens` 时 CLI 会告警，API 会置 `answer_truncated`。截断的答案不要当完整结果用。

---

## 其余工具

以下功能每次调用消耗 1 个通用额度，任何 token 都能用（包括自动注册的）。

### 渐进式阅读：搜索 → 判断 → 精读

按层读论文，避免 agent 为了回答一个关于 method 的问题而加载 50k tokens。

```bash
deepxiv search "agentic memory" --limit 5     # 1. 找候选
deepxiv paper 2409.05591 --brief              # 2. 值不值得读
deepxiv paper 2409.05591 --head               # 3. 结构与 token 分布
deepxiv paper 2409.05591 --section Method     # 4. 只读关键部分
```

- `--brief` —— 标题、TLDR、关键词、引用数、GitHub 链接
- `--head` —— 章节概览与 token 分布
- `--section NAME` —— 单个章节（`Introduction`、`Method`、`Experiments` …）
- `--preview` / `--raw` / *(无 flag)* —— 约 10k 字符预览 / 完整 markdown / 完整论文

### 搜索

```bash
deepxiv search "transformer" --limit 10 --format json

# 按作者 / 机构 / 分类过滤（逗号分隔）
deepxiv search "image generation" --authors "Shitao Xiao" --categories cs.CV --limit 5

# 按会议过滤（可重复传；NeurIPS ↔ NIPS 等别名自动匹配）
deepxiv search "diffusion model" --venue NeurIPS --venue-year 2025 --limit 5

# 按日期和引用数过滤（日期支持 YYYY、YYYY-MM、YYYY-MM-DD）
deepxiv search "diffusion models" --date-from 2024-01 --min-citations 50

# 高级日期模式：exact / after / before / between
deepxiv search "image generation" \
  --date-search-type between --date-str 2025-06-01 --date-str 2025-07-01

# 分页与按需精排
deepxiv search "LLM alignment" --limit 10 --offset 10
deepxiv search "transformer model" --use-fine-rerank
```

`--authors` 和 `--orgs` 既过滤也参与排序，`--categories` 只过滤。各条件之间是 `AND`，所以把很窄的日期区间叠加上很高的引用数门槛，完全可能合理地返回 0 条 —— 放宽其中一个即可。

返回 `{status, total_count, result: [...]}`。每条结果带 `arxiv_id`、`title`、`abstract`、`tldr`、`authors`、`categories`、`citation_count`、`date`、`github_url`、`score`，以及已入库时的 `venue` / `venue_year`。

### 人才库 —— 学者画像 <sub>`beta` · 源码安装</sub>

检索的对象是人而不是论文：谁在做某个方向、人在哪、履历如何。数据仍在建设中，
覆盖并不均匀 —— 尚未爬到的领域画像会比较薄。需要源码安装的 `1.1.0b1`（见开头的安装说明）。


```bash
# 语义检索（整句自然语言）
deepxiv talent search "做检索增强生成的青年老师" --semantic --limit 5

# 关键词模式：按人名 / 单位匹配
deepxiv talent search "窦志成"

# 按标签、职业阶段筛选，按引用量排序
deepxiv talent search --tags 大语言模型,Agent --career-stage student --sort total_citations

# 单人详情（ID 来自 search）
deepxiv talent survey 257
deepxiv talent survey 257 --format markdown    # 生成好的完整报告
deepxiv talent survey 257 --no-refresh         # 只读，不触发 Scholar 刷新
```

search 返回 `{persons, total, semantic, quota, cached}`；survey 返回
`{person, papers, scholar, quota}`，含教育经历、工作履历、联系方式、开源项目与
论文指标。画像超过 14 天会在 `survey` 时自动从 Google Scholar 刷新。

两个命令都从 `deepxiv ask` 那份 agent 配额里各扣 1 次（free 档 300 次/天），
因此需要注册过的 key。

### 其他数据源

```bash
deepxiv trending --days 7 --limit 30       # 最近最热的论文（社交信号）
deepxiv paper 2409.05591 --popularity      # 单篇的 views / tweets / likes

deepxiv pmc PMC544940 --head               # PubMed Central

deepxiv search "protein design" --biorxiv --limit 5     # bioRxiv / medRxiv
deepxiv biorxiv 10.1101/2021.02.26.433129 --format text
deepxiv medrxiv 10.1101/2020.03.24.20042937 --section Methods
```

## Agent 集成

### CLI Skill

```bash
mkdir -p $CODEX_HOME/skills
ln -s "$(pwd)/skills/deepxiv-cli" $CODEX_HOME/skills/deepxiv-cli
```

不支持原生 skill 的框架，直接把 [skills/deepxiv-cli/SKILL.md](skills/deepxiv-cli/SKILL.md) 作为操作说明加载。另有两个成型的工作流 skill：[热点摘要](skills/deepxiv-trending-digest/SKILL.md)、[baseline 表格](skills/deepxiv-baseline-table/SKILL.md)。

### 内置 Research Agent

用你自己的 LLM key 在本地跑 搜索 → 阅读 → 推理 的循环 —— 适合需要自己控制模型或循环逻辑的场景。`pip install "deepxiv-sdk[all]"` 安装，兼容任何 OpenAI 格式的 API。

```bash
deepxiv agent config
deepxiv agent query "最近关于 agent memory 的论文有哪些？" --verbose
```

### 自己包一个 MCP Server

deepxiv 不再自带 MCP server —— CLI 和 `Reader` 就是集成面，包一层大约二十行。真正值得抄的不是管道代码，而是下面这几条说明：只给 agent 一个裸的 `ask(query)` 工具，它会把这个 API 用得很差。

```python
from mcp.server.mcpserver import MCPServer   # mcp>=2.0；1.x 里叫 FastMCP
from deepxiv_sdk import Reader, agent_search_sources

mcp = MCPServer("deepxiv")
reader = Reader()

@mcp.tool()
def ask_arxiv(query: str, effort: str = "default") -> str:
    """回答一个研究问题，引用真实的 arXiv ID。

    适用于论文里的方法、数字、实验结果。时效信息、产品、非学术内容请用 ask_web。

    query 要具体 —— "what compression ratio does KV cache eviction report on
    LongBench" 有效，"kv cache" 无效。想要数字就明说（"what speedup" /
    "which benchmark"），这会让它去读论文正文而不是摘要。范围限定（年份、会议、
    分类、作者）写进 query 文本。中文可直接用。答非所问时换措辞重试 —— 调高
    effort 只增加读原文的轮数，改变不了首轮召回的方向。

    effort: "default"（最快）、"high"（对比论文）、"xhigh"（梳理演进）。
    """
    result = reader.agent_search(query, source="arxiv", effort=effort)
    answer = result["answer"]
    # sources 是召回集，是答案实际引用的超集
    cited = [p for p in agent_search_sources(result) if p["arxiv_id"] in answer]
    lines = [answer]
    if cited:
        lines += ["\n---\n引用的论文："] + [
            f"- [{p['arxiv_id']}] {p['title']}" for p in cited
        ]
    if result["stats"]["answer_truncated"]:
        lines.append("\n⚠️ 答案被截断 —— 不要当完整结果用。")
    return "\n".join(lines)

if __name__ == "__main__":
    mcp.run(transport="stdio")
```

有四件事必须写进工具描述，否则 agent 会误用结果：

1. **引用是真的** —— 服务端从不编造 ID，没有就直说"没有"。告诉 agent 把这些 ID 原样保留给用户。
2. **`sources` 是召回集不是引用列表** —— 按上面的方式筛出答案里出现过的 ID，否则 agent 会把无关论文当成证据摆出来。
3. **web 后端的证据分两档** —— `read: true` 的页面读过正文，其余只贡献了一条搜索摘要。把这个区分传下去，agent 才能对弱证据加限定词。
4. **`answer_truncated` 意味着不完整** —— 必须明说，否则 agent 会把一个被截断的答案当完整结论来总结。

要做 web 版工具，把 `source` 换成 `"web"`，加上 `search_type`（`search` / `scholar` / `news` / `images`），并改用 `page["url"] in answer` 而不是 `arxiv_id` 来匹配。

---

## Token 与额度

deepxiv 依次从 `--token`、`DEEPXIV_TOKEN`、`~/.env` 解析 token，首次使用会自动注册一个。

| | 通用 daily limit | Agentic / talent 调用 | 获取方式 |
|---|---|---|---|
| 自动注册 | 1,000 请求 | ❌ 不可用 | 首次使用 CLI 时自动完成 |
| 注册用户 | 10,000 请求 | ✅ 300 次/天 | [data.rag.ac.cn/register](https://data.rag.ac.cn/register) |
| 自定义 | 联系我们 | 联系我们 | 邮件 `tommy[at]chien.io` |

两份额度相互独立：agentic 调用不消耗通用额度，反之亦然。找回 key：[data.rag.ac.cn/token-lookup](https://data.rag.ac.cn/token-lookup)（支持 Google 注册，方便没有中国手机号的用户）。

免费测试论文（无需 token）—— arXiv：`2409.05591`、`2504.21776`；PMC：`PMC544940`。

## Python SDK

CLI 覆盖了大部分场景。Python API —— agentic search（阻塞与流式）、渐进式阅读、批处理、错误处理 —— 见 **[USAGE.zh.md](USAGE.zh.md)**。

```python
from deepxiv_sdk import Reader

reader = Reader()
result = reader.agent_search("what speedup does DEER report on HumanEval")
print(result["answer"])
```

## 常见问题

- **`ask` 返回 403？** 你用的是自动注册的 token。Agentic search 需要注册 key，见上文。
- **`ask` 出字慢？** 只有 `--effort default` 以 5s 内首字为目标，`high`/`xhigh` 会刻意多取证。
- **`ask` 答非所问？** 换个更具体的措辞，而不是调高 `--effort` —— effort 只加读原文的轮数，改不了首轮召回方向。
- **`ask` 列出的论文和答案无关？** 那是召回集，不是引用列表，`--all-sources` 可看全。
- **搜索返回 0 条？** 放宽过滤条件 —— 日期和引用数叠加起来收窄得很快。
- **超时？** `Reader` 默认退避重试 3 次，可用 `Reader(timeout=120, max_retries=5)` 调整。`agent_search*` 按设计从不自动重试。
- **Agent 报 `Reasoning content is only supported as the last assistant message`？** 推理模型在多轮工具调用时要关掉 thinking：`deepxiv agent query "…" --disable-thinking`，或 `Agent(..., enable_thinking=False)`。
- **`agent.add_paper()` 加新论文失败？** 论文还没入库时返回 `False`，1–3 天内的论文经常还没入库。

## 覆盖范围

| 数据源 | 状态 |
|---|---|
| arXiv | ✅ 全文，T+1 同步 |
| Web | ✅ Google + 已缓存网页正文 |
| PubMed Central | ✅ 生物医学与生命科学 |
| bioRxiv / medRxiv | ✅ 生物 / 医学预印本 |

DeepXiv 专注开放获取文献，让 agent 基于可直接访问的数据工作，而不是被订阅墙卡住。

## 示例

查看 [examples/](examples/)：`example_ask.py`、`quickstart.py`、`example_reader.py`、`example_agent.py`、`example_advanced.py`、`example_error_handling.py`。

## 许可证 & 支持

MIT License，见 [LICENSE](LICENSE)。

- 🌐 **正式系统**: [deepxiv.com](https://deepxiv.com)
- 🐛 **GitHub Issues**: [github.com/qhjqhj00/deepxiv_sdk/issues](https://github.com/qhjqhj00/deepxiv_sdk/issues)
- 📚 **API 文档**: [data.rag.ac.cn/api/docs](https://data.rag.ac.cn/api/docs)
- 🚦 **实时状态**: [data.rag.ac.cn/status](https://data.rag.ac.cn/status)
- 📧 **更高额度**: 邮件 `tommy[at]chien.io` 说明用途
