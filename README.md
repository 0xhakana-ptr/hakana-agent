# QuestionForge

面向 **CCF/TPCTF 2026 智能体团队赛道 · 出题阶段** 的自主出题 Agent。

QuestionForge 不是一个让大模型直接生成整个仓库的 prompt。它把“创意”和“可执行的题目工程”拆开：

- 大模型负责读主题、比较机制、改写叙事、提出难度估计和做对抗审查；默认优先使用受限 Claude Code CLI，并保留直连模型网关的降级路径；
- 确定性配方编译器负责生成服务、Compose、动态答案、附件和参考解；
- 规则检查器和官方 CTFY 工具负责判断题目是否能被平台接受；
- 盲解标定器负责测量题目是否落在 5%–25% 的高分难度区间；
- fact/intent 图负责保存整个过程的证据和状态。

> 本项目只用于赛事、教学和明确授权的安全测试。生成的题目服务本身故意包含 CTF 漏洞，只能部署在比赛或隔离测试环境。

## 1. 设计目标

出题阶段同时存在四个相互制约的目标：

1. **可启动**：题目必须在全新实例中完成构建、启动并通过健康检查。
2. **可复现**：参考解必须从服务本身拿到该实例动态铸造的全部答案。
3. **可审核**：答案不能泄漏，不能依赖公网或平台模型，不能操纵未来的解题 Agent。
4. **有竞争力**：题目最终全解率应尽量落在计分曲线的满分区间。

官方计分曲线为：

| 总体全解率 | 出题乘数 |
|---|---:|
| 0% | 0.20 |
| 5% | 1.00 |
| 5%–25% | 1.00 |
| 25%–100% | 从 1.00 线性下降到 0.30 |
| 100% | 0.30 |

因此 QuestionForge 不追求“零解”或“越难越好”，而是默认瞄准约 **8%–20%** 的强队全解率。平台自动审核只认可真实的动态答案捕获，所以“可复现”永远优先于无法验证的复杂创意。

## 2. 总体架构

```text
                          ┌──────────────────────────┐
                          │ 比赛平台 / task.json /   │
                          │ 环境变量 / 本轮主题      │
                          └────────────┬─────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────┐
│ Orchestrator                                                    │
│ 读取配置 → 记录主题 → 规划候选 → 编译 → 审查 → 标定 → 上传    │
└───────┬───────────────┬────────────────┬───────────────┬────────┘
        │               │                │               │
        ▼               ▼                ▼               ▼
┌──────────────┐ ┌──────────────┐ ┌─────────────┐ ┌──────────────┐
│ Fact/Intent  │ │ ModelClient  │ │ Planner     │ │ Platform API │
│ Graph        │ │ Claude Code  │ │ 6 candidates│ │ check/upload │
│ facts/intents│ │ or direct API│ │ normalize   │ │ poll/review  │
└──────────────┘ └──────────────┘ └──────┬──────┘ └──────────────┘
                                          │
                                          ▼
                              ┌─────────────────────────┐
                              │ Recipe Compiler         │
                              │ 4 个题目机制 × 3 难度层 │
                              └────────────┬────────────┘
                                           │
                                           ▼
┌─────────────────────────────────────────────────────────────────┐
│ Verification Pipeline                                           │
│ 内部静态规则 → ctfy authoring check → 可选 Docker smoke         │
│ → 对抗审查 → 可选盲解标定 → 必要时自动调难并重新验证            │
└─────────────────────────────────────────────────────────────────┘
```

这是一个**单进程编排架构**。主调度、验证和落盘都在一个 Python 进程内；模型推理有两种后端：

1. 优先：短生命周期的无头 Claude Code CLI 子进程；
2. 降级：直接调用 Anthropic/OpenAI-compatible HTTP API。

没有 Kali 镜像、tmux Agent 军团或 Codex CLI。Claude Code 的工具、WebFetch 和会话持久化全部关闭，它只输出分析结果，不直接修改题目文件。

## 3. 代码分层

| 层 | 职责 | 主要文件 |
|---|---|---|
| CLI / 配置 | 子命令、环境变量、运行参数 | `src/questionforge/cli.py`, `config.py` |
| 编排 | 完整状态推进、时限控制、失败处理 | `orchestrator.py` |
| 认知层 | Claude Code / 直连网关、选题、审查、修复 | `llm.py`, `claude_cli.py`, `planner.py`, `prompts.py` |
| 记忆层 | fact/intent 事实图与状态证据 | `graph.py` |
| 题目编译层 | 将 Blueprint 编译为 CTFY 包 | `recipes/` |
| 验证层 | 静态审计、官方检查、本地 smoke | `verify.py` |
| 难度标定层 | 盲解、全解率统计、自动升降难 | `calibration.py` |
| 平台层 | dry-run、上传、审核轮询 | `platform.py` |
| 输出层 | 打包、结果 JSON、Markdown 报告 | `package.py`, `report.py` |

## 4. 核心数据模型

### 4.1 Blueprint

`Blueprint` 描述“要出什么题”，而不是直接描述一堆文件：

```text
slug / title / description / category / difficulty
recipe id / theme / intended path / anti-shortcuts
question list / recipe parameters / estimated solve rate
```

其中：

- `description` 和题面是玩家可见内容；
- `intended` 是作者和审核者可见的秘密解题路径；
- `parameters` 只能包含具体配方允许的参数；
- `estimated_agent_solve_rate` 只是先验，不等同于实测结果。

### 4.2 Question

每个题默认包含两个动态问题：

```text
checkpoint   第一阶段答案
master_key   requires: [checkpoint] 的最终答案
```

平台对“完整解出”的定义是所有计价问题均已解决。因此双阶段题目比单 Flag 更容易控制全解率。

### 4.3 Fact / Intent

`FactGraph` 是 Sapper V2 思路的迁移版：

- **Fact**：已经确认的事实，例如主题、选中的 Blueprint、文件哈希、官方检查结果、smoke 结果、上传状态；
- **Intent**：要执行的工作单元，例如编译、验证和提交；
- 每个节点存为独立 JSON 文件；
- 写入使用临时文件 + `os.replace`；
- 并发写由独占锁保护；
- `sapper graph` 风格的命令由 `questionforge graph` 提供。

当前实现会持久化这些事实，但尚未实现“从旧 run 自动恢复并继续调度”的完整 resume 状态机；重启后会创建新的 run 目录。事实图仍可用于复盘和迁移。

## 5. 模型层

### 5.1 模型接入

`AUTHORING_MODEL_BACKEND` 支持三种模式：

| 值 | 行为 |
|---|---|
| `auto` | Claude Code 可用时优先使用，失败后降级到 direct HTTP |
| `claude_cli` | Claude Code 优先，direct 可用时作为第二降级 |
| `direct` | 只使用直连 API |

直连后端支持：

- OpenAI-compatible `/v1/chat/completions`
- Anthropic-compatible `/v1/messages`

相关环境变量：

```text
LLM_FLAVOR=openai|anthropic
LLM_BASE_URL=...
LLM_API_KEY=...
LLM_MODEL=...
AUTHORING_MODEL_BACKEND=auto
CLAUDE_BIN=claude
CLAUDE_CODE_TIMEOUT=300
```

每次调用都有重试和退避；输入输出、实际使用的 backend、成本或 usage 元数据会保存到 run 的 `model/` 目录，但不会写入 API key。

Claude Code 后端固定使用以下安全参数：

```text
--bare
--restricted
--tools ""
--permission-mode dontAsk
--permission-prompts none
--no-session-persistence
```

含义：

- 不加载仓库中的 CLAUDE.md、hooks、skills、plugins 或用户配置；
- 不开放 Bash、Read、Edit、Write、WebFetch 等工具；
- 不保留会话；
- 不读取订阅登录状态，只使用本次 run 的平台 token；
- 不使用 `--dangerously-skip-permissions`。

因此 Claude Code 在这里是**高质量推理引擎**，不是能修改宿主机的自治编码进程。

### 5.2 四种认知角色

这些是同一模型 backend 上的不同提示角色，不是四个常驻进程。每个角色都会启动一次独立的无头 Claude Code 调用，或走一次 direct HTTP 调用：

1. **Strategic planner**
   - 读取本轮主题和配方目录；
   - 生成最多 8 个候选，默认要求 6 个；
   - 覆盖不同机制与难度层；
   - 不允许发明未登记 recipe。

2. **Adversarial reviewer**
   - 检查答案泄漏、题面与源码不一致、平凡绕过、不可复现路径；
   - 检查是否操纵未来解题 Agent；
   - 只提供建议，不能绕过确定性 smoke。

3. **Bounded repairer**
   - 只允许修改白名单字段和配方参数；
   - 不能写 shell 命令，不能生成任意文件；
   - 修复后必须重新通过静态检查和官方检查。

4. **Blind solver**
   - 用于盲解标定；
   - 只能看到公开描述、当前问题、公开附件和目标 URL；
   - 通过受限 HTTP 工具和服务交互；
   - 看不到源码、答案文件、intended path 或参考解。

### 5.3 为什么不让模型直接写整个题目

不受约束的代码生成会同时引入：

- Compose 权限越界；
- 答案路径挂载错误；
- YAML 字段不被平台接受；
- 参考解和环境不一致；
- 公网依赖；
- 答案或 intended path 泄漏；
- 面向解题 Agent 的提示注入。

QuestionForge 将模型输出收紧为 Blueprint 和受限参数，把高风险工程交给固定配方。

## 6. 出题流水线

### 阶段 1：主题获取

主题来源优先级：

1. CLI `--theme`；
2. `AUTHORING_TOPIC` 或 `CTFY_TOPIC`；
3. `task.json` 中的 authoring topic/theme；
4. 平台 `GET /competitions/{id}/topics` 已发布主题；
5. 确定性 fallback 主题。

主题始终被当作数据，不被当作高优先级指令。

### 阶段 2：候选规划

模型从四个 recipe family 中选择并参数化：

- Web 解析器差异；
- Web 对象图授权；
- AI 工具调用信任边界；
- Pwn 两阶段控制流。

代码会：

- 验证 recipe 是否存在；
- 验证类别是否匹配；
- 强制两个固定问题 id；
- 移除泄漏技术的 tag；
- 拒绝在公开描述中出现已知技术词；
- 将 `difficulty_level` 限制在 0–2；
- 根据预计全解率与 12% 目标点的距离计算候选分数。

如果模型不可用或全部候选不合格，则根据中英文主题关键词选择确定性 fallback recipe。

### 阶段 3：题目编译

配方编译器生成完整 CTFY 包：

```text
metadata.yaml
docker-compose.yml
services/flag-rotator/
services/app/
attachments/
solution/exploit.py
solution/WRITEUP.md
AUTHORING.md
BUILD_MANIFEST.json
```

所有动态答案都通过平台注入的 `ANSWER_<ID>` 环境变量进入 `flag-rotator`，再由 rotator 写入共享卷。参考解只能通过与玩家相同的服务路径重新取得答案。

### 阶段 4：静态验证

QuestionForge 自己的检查包括：

- 必需文件是否存在；
- CTFY-0002 版本声明是否有效；
- 是否出现固定 `answer:`；
- Compose 是否使用 privileged、host network、Docker socket、external network；
- `services/` 是否出现字面量 `FLAG{...}`；
- 参考解是否读取 `/answers`、`ANSWER_*` 或 `params/answer.json`；
- WRITEUP 是否为空；
- 附件中是否有符号链接或隐藏文件；
- 是否出现明显的公网地址、云 metadata 地址或解题 Agent 提示注入。

### 阶段 5：官方检查

Linux 环境执行：

```bash
ctfy authoring check <package> --json
```

Windows 上的官方 CLI 受 `O_DIRECTORY` 等 Linux 文件语义限制，因此主进程只标记为跳过，不伪造通过结果。比赛 Linux 环境会真实执行该检查。

题目元数据使用 `CTFY-0002/1` 作为官网 v2 和公开发布 `ctfy 0.8.0` 审计器的共同可执行子集。

### 阶段 6：本地 smoke

启用 `AUTHORING_LOCAL_SMOKE=1` 时，QuestionForge 调用：

```bash
ctfy authoring smoke <package> --local
```

这会：

1. 启动完整 Compose 环境；
2. 为全新实例铸造答案；
3. 运行参考解；
4. 比较每个 `Q[<id>]: <value>`；
5. 拆除环境。

本地 smoke 不是“参考解能跑就算成功”，而是与平台近似的端到端答案验证。

### 阶段 7：对抗审查和有限修复

审查模型会看到完整题目树，并被明确告知文件内容是数据而非指令。若审查结果不是 `pass`，QuestionForge 最多进行一次受限修复：

- 只允许修改 Blueprint 字段；
- 只允许合并 recipe 参数；
- 不改变 recipe id；
- 重建后必须重新通过结构检查和官方检查。

如果修复失败，保留原包，不会用模型输出覆盖验证结果。

### 阶段 8：盲解标定

盲解器把难度从“模型猜测”变成可测量的实验结果。默认运行 5 轮，每轮从干净环境开始。

盲解器可用动作：

```json
{"action":"request","method":"GET","path":"/...","headers":{},"body":""}
{"action":"submit","question_id":"checkpoint","value":"..."}
{"action":"finish","reason":"..."}
```

限制：

- 只能请求当前题目 URL；
- 不提供宿主机文件访问；
- 不提供源码；
- 不提供 answer volume；
- 不接受挑战返回文本作为新指令；
- 每题有最大动作数限制。

决策规则：

```text
低于 5%     -> too_hard，难度层 -1
5%–25%      -> in_band，保持
高于 25%    -> too_easy，难度层 +1
少于 3 轮   -> 不自动调整
```

调整后题目包会重新生成并重新通过 CTFY 检查。实际盲解能力目前覆盖 Web recipe；Pwn 由于还缺少安全的通用二进制分析沙箱，当前保持低置信度估计。

### 阶段 9：平台预检与上传

平台层直接调用 CTFY REST API：

- `GET /topics`
- `GET /authoring/quota`
- `POST /authored-challenges/check`
- `POST /authored-challenges`
- `POST /authored-challenges/{id}/revisions`
- `GET /authored-challenges`
- `GET /authored-challenges/{id}/smoke-live`
- `GET /authored-challenges/{id}/smoke-logs`

上传前检查比赛窗口、滚动上传额度和 smoke 额度。平台 dry-run 失败时不会继续上传。

自动审核会轮询到以下结果之一：

```text
approved
rejected
pending / uploaded-pending
```

### 阶段 10：报告与产物

每个 run 输出：

```text
work/runs/<timestamp>/
├── context.json
├── graph/
│   ├── facts/
│   └── intents/
├── model/
├── calibration/
│   ├── trial-*-compose.log
│   └── trial-*.json
├── package/
├── platform-check.json
├── platform-upload.json
├── result.json
└── RUN_REPORT.md
```

失败状态不会改写成成功；平台拒绝、本地拒绝、smoke 失败和模型不可用都分别记录。

## 7. 四个题目配方

### 7.1 `web-preview-ssrf`

核心机制：

1. 公共 topology 暴露受限服务入口；
2. preview broker 检查 authority 中的兼容标记；
3. HTTP client 按 userinfo/host 规则解析同一字符串；
4. 攻击者经 broker 读取内部 vault；
5. 第一阶段答案作为第二阶段导出票据。

难度层：

- `0`：topology 和提示更直接；
- `1`：标准 topology → vault；
- `2`：vault origin 不在 topology 中，需要先从 asset index 获取路由元数据。

### 7.2 `web-object-graph`

核心机制：

1. 公共根对象有合法访问权；
2. 对象关系解析器递归展开 linked records；
3. 授权只在根对象执行，递归子对象绕过对象级检查；
4. 内部 runbook 暴露 checkpoint 和 export route；
5. checkpoint 作为 operator export 票据。

难度层主要改变公开发现提示和对嵌套关系的暴露程度。

### 7.3 `ai-tool-agent`

核心机制：

1. 用户可写入 workspace memory；
2. assistant 在总结时检索这些 memory；
3. 检索内容跨入“可信模型输出”的工具解析路径；
4. 第一阶段触发 `vault.checkpoint`；
5. 第二阶段把 checkpoint 作为 `vault.export` 的 ticket。

这是完全本地的确定性 assistant，不依赖平台模型。难度层 2 要求把同一工具指令拆成两个 memory 片段；单独一个片段无法解析，必须理解并重建检索上下文。

### 7.4 `pwn-stack-chain`

核心机制：

1. 原生 TCP 服务有两个脆弱栈帧；
2. 第一帧跳到 checkpoint；
3. 第二帧跳到 master_key；
4. 两个答案都从服务自己的 `/answers` 只读挂载中输出。

难点包括识别第一帧和第二帧不同的栈布局。难度层 2 不在初始 banner 暴露 master_key 地址，必须完成第一帧后取得第二阶段地址。

## 8. 为什么采用“配方编译器”而不是任意代码生成

配方编译器的优势：

- 每个机制都有固定、已通过 smoke 的参考解；
- 动态答案交付方式一致；
- Compose 面只暴露白名单键；
- 模型错误最多影响标题、叙事和参数，不会直接改坏答案卷；
- 可在机制内自动升降难；
- 可对不同轮次生成不同组合。

代价：

- 原创性上限由配方库决定；
- 强队可能识别这些漏洞家族；
- 新机制必须由开发者显式加入并通过 smoke。

因此后续提升重点应是增加机制族和自动组合，而不是放宽模型直接写代码的权限。

## 9. 运行模式与降级策略

| 条件 | 行为 |
|---|---|
| 模型可用 | 6 候选规划、对抗审查、受限修复 |
| 模型不可用 | 关键词分类 + 确定性 recipe fallback |
| Claude Code 可用 | 无工具 Claude Code 后端优先 |
| Claude Code 调用失败 | 如配置了 direct API，则自动回退 |
| Linux + `ctfy` | 执行官方本地审计和可选 smoke |
| Windows | 跳过 Linux-only 本地审计，保留标记 |
| 平台凭据可用 | 平台 dry-run、上传和审核轮询 |
| 平台凭据缺失 | 产出可上传包和报告，不尝试上传 |
| Docker 可用 + 模型可用 | Web 盲解实跑 |
| 外部测试目标 | 只做保守单轮标定，不因单轮结果自动调难 |
| 平台自动 smoke 返回 `errored` | 记录为平台问题，不误判题目 |

## 10. 安全边界

- 不访问公网作为题目运行依赖；
- 不依赖平台提供的大模型；
- 不攻击 CTFY、worker、LAN、cloud metadata 或其他队伍；
- 不把答案写进服务源码；
- 不允许参考解直接读取答案卷；
- 不把 `AUTHORING.md` 或 intended path 发送给玩家；
- 不允许盲解 Agent 读取源码或本地文件；
- Claude Code 后端禁用全部工具，模型不能直接执行 shell 或修改文件；
- 上传 token 和模型 key 只从环境变量读取，不写入 run 目录。

完整威胁模型见 [docs/THREAT_MODEL.md](docs/THREAT_MODEL.md)。

## 11. 快速开始

安装：

```bash
python -m pip install -e .
```

离线构建一个标准题：

```bash
python -m questionforge build \
  --theme "AI agents and untrusted operational memory" \
  --recipe ai-tool-agent \
  --difficulty-level 1 \
  --output work/demo
```

验证和打包：

```bash
python -m questionforge verify work/demo --no-ctfy
python -m questionforge pack work/demo --output work/demo.tar.gz
```

安装官方审计器：

```bash
python -m pip install "ctfy[author]==0.8.0"
ctfy authoring check work/demo
```

构建本地 QA runner：

```bash
docker build -f tools/ctfy-exploit-runner.Dockerfile \
  -t ctfy-exploit-runner:local .

ctfy authoring smoke work/demo --local \
  --runner-image ctfy-exploit-runner:local
```

执行完整自主流程：

```bash
export CTFY_PLATFORM_URL='https://ctfy.tsinghua.edu.cn'
export CTFY_TOKEN='...'
export AUTHORING_COMPETITION_ID='c0d8b4e3dd3b42c095d63d7dfa66431f'
export LLM_FLAVOR='openai'
export LLM_BASE_URL='https://...'
export LLM_API_KEY='...'
export LLM_MODEL='...'

python -m questionforge run --deadline-minutes 540
```

## 12. 配置

### 平台

```text
CTFY_PLATFORM_URL
CTFY_TOKEN
AUTHORING_COMPETITION_ID
AUTHORING_TOPIC
AUTHORING_DEADLINE_MINUTES=540
AUTHORING_WORK_DIR=work
```

### 模型

```text
LLM_FLAVOR=openai|anthropic
LLM_BASE_URL
LLM_API_KEY
LLM_MODEL
AUTHORING_MODEL_BACKEND=auto
CLAUDE_BIN=claude
CLAUDE_CODE_TIMEOUT=300
```

### 验证

```text
AUTHORING_LOCAL_SMOKE=0|1
AUTHORING_VERBOSE=0|1
```

### 盲解标定

```text
AUTHORING_CALIBRATION=1
AUTHORING_CALIBRATION_TRIALS=5
AUTHORING_CALIBRATION_TURNS=16
AUTHORING_CALIBRATION_TARGET=
AUTHORING_CALIBRATION_ANSWERS=
```

`AUTHORING_CALIBRATION_ANSWERS` 只存在本机环境中，不进入盲解提示词。

## 13. Docker 运行

```bash
docker build -t questionforge:latest .

docker run --rm \
  -e CTFY_PLATFORM_URL \
  -e CTFY_TOKEN \
  -e AUTHORING_COMPETITION_ID \
  -e LLM_FLAVOR \
  -e LLM_BASE_URL \
  -e LLM_API_KEY \
  -e LLM_MODEL \
  questionforge:latest
```

Agent 本体使用非 root `python:3.12-slim-bookworm`，镜像中安装：

- Claude Code CLI `2.1.323`
- QuestionForge Python 运行时

镜像不包含 Kali 工具链或 Codex CLI。

## 14. 命令

```bash
python -m questionforge run
python -m questionforge build
python -m questionforge plan
python -m questionforge verify
python -m questionforge pack
python -m questionforge graph
python -m questionforge doctor
```

## 15. 当前验证状态

- 20 项单元测试通过；
- 4 个 recipe family；
- 7 个默认/强化变体通过官方 `ctfy authoring check`；
- 7 个变体通过官方 `ctfy authoring smoke`，均捕获 `2/2` 动态答案；
- blind HTTP solver 工具循环已用本地真实服务做过程级测试；
- Agent Docker 镜像构建和容器内 dry-run 通过。
- 容器内 `claude --version` 返回 `2.1.323 (Claude Code)`。

详细记录见 [docs/VALIDATION.md](docs/VALIDATION.md)。

## 16. 已知限制

1. 当前是单 run 编排，fact graph 可复盘，但还没有自动从旧 run 恢复调度。
2. 盲解实跑当前支持 Web 题目；Pwn 需要额外的受限二进制分析与交互沙箱。
3. 外部测试目标默认只跑单轮标定，不把单轮结果用于自动难度调整。
4. 原创机制仍取决于 recipe library 的覆盖范围。
5. 本地 Windows 无法执行官方 `ctfy` 的 Linux-only 检查；比赛 Linux 环境会执行。
6. 是否获奖取决于最终参赛队伍、主题匹配和真实解题分布，架构只能提高稳定性与命中 5%–25% 区间的概率。

## 17. 研究依据

设计参考了 Sapper V2 的 fact/intent 历史、角色分工和自愈思想，以及 CTF Agent、D-CIPHER、Cybench、CyberGym、CTFusion 等公开工作。

- [架构设计说明](docs/DESIGN.md)
- [盲解标定设计](docs/CALIBRATION.md)
- [比赛和官方规则摘要](docs/COMPETITION_REQUIREMENTS.md)
- [安全与威胁模型](docs/THREAT_MODEL.md)
- [主要资料来源](docs/SOURCES.md)
- [验证记录](docs/VALIDATION.md)
