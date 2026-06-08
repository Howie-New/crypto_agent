# x402 Agent Demo

**基于 x402 协议与 MCP 架构的自主经济 AI Agent**

*Design and Implementation of an Autonomous Economic AI Agent Based on x402 Protocol and MCP Architecture*

---

## 🎯 项目简介

这是一个创新的 AI Agent 演示项目，展示了如何让 AI 自主地发现付费服务、评估价格、执行加密货币支付并获取内容。项目结合了三个前沿技术：

- **x402 协议** - 基于 HTTP 402 状态码的 Web3 支付标准
- **MCP (Model Context Protocol)** - Anthropic 推出的 AI 工具调用协议
- **多模型支持** - Claude API / OMLX 本地模型（Qwen3-Coder、Qwen3.6）/ Ollama（Gemma 3）
- **双界面** - 终端交互 + Chainlit Web UI

### 核心能力

✅ 自动检测 HTTP 402 付费墙  
✅ 解析支付需求（金额、地址、描述）  
✅ 基于策略自主决策是否支付  
✅ 执行 Web3 加密货币交易  
✅ 获取付费内容并呈现给用户  
✅ 发现 Coinbase x402 Bazaar 中的真实 x402 服务  
✅ Dry-run 探测真实 x402 URL 的支付要求（不签名、不付款）  

---

## 🏗️ 系统架构

```
┌─────────────────────────────────────┐
│   AI Agent Client (LLMProvider)    │
│   - 任务理解                         │
│   - 支付决策                         │
│   - 用户交互                         │
└─────────────────────────────────────┘
              ↓
┌─────────────────────────────────────┐
│   MCP Server (stdio 工具层)           │
│   ├─ http_request                   │
│   ├─ web3_payment                   │
│   ├─ get_wallet_balance             │
│   ├─ check_payment_policy           │
│   ├─ discover_x402_services         │
│   └─ real_x402_request              │
└─────────────────────────────────────┘
              ↓
┌──────────────────────────────────────────┐
│   x402 Service Layer                     │
│   ├─ Mock x402 Service (Flask)           │
│   ├─ Coinbase x402 Bazaar Discovery      │
│   └─ Real x402 URL Probe (dry-run only)  │
└──────────────────────────────────────────┘
```

---

## 📦 项目结构

```
x402-agent-demo/
├── agent-client/            # AI Agent 客户端
│   └── agent.py             # Agent 核心（LLMProvider + MCP Client + 支付策略）
├── mcp-server/              # MCP Server (工具提供者)
│   └── server.py            # 6 个 MCP 工具实现
├── mock-service/            # Mock x402 付费服务
│   └── app.py               # Flask API（3 个付费端点 + 服务列表）
├── run_mock_service.py      # 启动 Mock 服务
├── run_agent.py             # 启动终端 Agent
├── chainlit_app.py          # Chainlit Web UI
├── setup.py                 # 快速设置脚本
├── .env.example             # 环境变量模板
├── pyproject.toml           # 项目配置（uv 管理）
└── README.md                # 本文档
```

---

## 🚀 快速开始

### 前置要求

- Python 3.11+
- Node.js v22+ (如需使用 MCP)
- uv (Python 包管理器)
- Anthropic API Key 或 OpenAI-compatible 本地模型服务

### 1. 安装依赖

```bash
# 克隆项目后进入目录
cd x402-agent-demo

# 使用 uv 同步依赖
uv sync
```

### 2. 配置环境

```bash
# 运行设置脚本（会自动生成测试钱包和 .env 文件）
uv run python setup.py
```

或者手动创建 `.env`：

```bash
cp .env.example .env
```

编辑 `.env` 文件，选择模型提供方。

**Anthropic / B.AI Claude-compatible：**

```env
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-xxxxx
```

**OpenAI-compatible 本地模型，例如 Ollama / OMLX / MLX wrapper：**

```env
LLM_PROVIDER=openai
OPENAI_BASE_URL=http://127.0.0.1:8000/v1
OPENAI_API_KEY=your_local_api_key
OPENAI_MODEL=your_local_model_id
```

### 3. 启动服务

需要三个终端窗口：

**终端 1 — Mock x402 服务**

```bash
uv run python run_mock_service.py
# 默认端口由 .env 中 MOCK_SERVICE_PORT 决定（默认 5000）
```

**终端 2 — 终端交互 Agent**

```bash
uv run python run_agent.py
```

**终端 3 — Chainlit Web UI**

```bash
uv run chainlit run chainlit_app.py --host 127.0.0.1 --port 7860
# 浏览器打开 http://127.0.0.1:7860
```

> 如果本地模型通过代理访问有问题，在命令前加 `NO_PROXY="*"`。

---

## 💡 演示用例

以下用例可直接复制粘贴到 Chainlit Web UI 或终端 Agent 中执行。端口号请根据 `.env` 中的 `MOCK_SERVICE_PORT` 调整（下文以 5050 为例）。

### 1. 查看钱包余额

```
查看当前 Agent 钱包余额，说明可用资金情况。
```

预期：Agent 调用 `get_wallet_balance`，返回 ETH 和 USDC 余额。

### 2. 发现本地可用付费服务

```
访问 http://localhost:5050/api/services 查看有哪些付费服务可用，列出每个服务的名称、价格和调用方式。
```

预期：Agent 调用 `http_request`，返回 3 个付费端点（文章 0.5 USDC、图片 0.8 USDC、视频 5.0 USDC）。

### 3. 402 检测 — 只探测不支付

```
访问 http://localhost:5050/api/article/quantum-2026 ，只告诉我返回了什么状态码和支付要求信息，不要执行支付。
```

预期：Agent 调用 `http_request`，检测到 HTTP 402，展示金额、收款地址、challenge 等支付信息。

### 4. 支付策略检查

```
检查 0.5 USDC 和 5.0 USDC 两个金额分别是否需要用户审批，说明自动支付阈值。
```

预期：Agent 调用 `check_payment_policy` 两次，0.5 USDC 自动批准，5.0 USDC 需要人工确认。

### 5. 小额自动支付完整闭环（核心场景）

```
获取付费文章 http://localhost:5050/api/article/quantum-2026 ，如果需要支付就自动完成并展示文章内容。
```

预期：Agent 依次调用 `http_request`（检测 402）→ `web3_payment`（模拟支付 0.5 USDC）→ `http_request`（携带凭证重试获取内容）。

### 6. 大额支付触发人工确认

```
请访问 http://localhost:5050/api/generate/video 生成一段4K视频，POST请求body为 {"prompt": "cyberpunk city at night"}。如果需要支付就按流程处理。
```

预期：Agent 检测到 5.0 USDC 超出自动批准额度，提示用户确认支付。

### 7. 发现真实 x402 服务（Coinbase Bazaar）

```
搜索真实的 x402 付费服务，关键词 "crypto price data"，最多返回 5 条，列出每个服务的名称、URL和价格。
```

预期：Agent 调用 `discover_x402_services`，从 Coinbase x402 Bazaar 返回真实服务列表。

### 8. 真实 x402 端点探测（Dry-run）

```
用 real_x402_request 工具探测 https://api.brianknows.org/api/v0/agent/knowledge 这个真实 x402 端点，解析它的支付要求（EIP-712 签名结构、金额、收款链），不要实际支付。
```

预期：Agent 调用 `real_x402_request`，展示真实 HTTP 402 支付要求结构（accepts、paymentRequirements 等）。

### 9. 多步骤组合任务

```
请完成以下任务：1) 先查询钱包余额；2) 然后访问 http://localhost:5050/api/article/quantum-2026 获取付费文章；3) 最后搜索 3 个真实 x402 服务。每一步都告诉我结果。
```

预期：Agent 按顺序执行三个子任务，展示完整的工具调用链。

---

## 🔧 可用的 API 端点

### Mock x402 Service

| 端点 | 方法 | 价格 | 描述 |
|------|------|------|------|
| `/api/services` | GET | 免费 | 列出所有付费服务及价格 |
| `/api/article/<id>` | GET | 0.5 USDC | 高级研究文章 |
| `/api/generate/image` | POST | 0.8 USDC | AI 图片生成 |
| `/api/generate/video` | POST | 5.0 USDC | AI 视频生成 |
| `/health` | GET | 免费 | 健康检查 |

### Real x402 Discovery / Probe

| MCP 工具 | 作用 | 是否付款 |
|------|------|------|
| `discover_x402_services` | 调 Coinbase x402 Bazaar discovery/search，发现真实 x402 服务 | 否 |
| `real_x402_request` | 对真实 x402 URL 请求一次，解析 HTTP 402 payment requirements | 否 |

当前真实 x402 功能处于 **dry-run** 阶段：只发现服务、请求 URL、解析 402 支付要求、展示金额/币种/网络/服务信息，不会签名，也不会产生链上支付。

### 测试请求

```bash
# 测试付费墙
curl http://localhost:5000/api/article/test-123

# 带支付凭证的请求
curl http://localhost:5000/api/article/test-123 \
  -H 'X-Payment-Proof: {"tx_hash": "0x1234567890abcdef"}'
```

---

## ⚙️ 支付策略配置

在 `.env` 文件中配置：

```env
# 免密支付额度（USDC）
MAX_AUTO_APPROVE_AMOUNT=1.0

# 钱包配置
AGENT_WALLET_ADDRESS=0x...
AGENT_PRIVATE_KEY=0x...

# Web3 RPC (Sepolia 测试网)
WEB3_RPC_URL=https://eth-sepolia.g.alchemy.com/v2/demo

# Real x402 discovery / dry-run
X402_BAZAAR_BASE_URL=https://api.cdp.coinbase.com/platform/v2/x402/discovery
ALLOW_REAL_X402_PAYMENT=false
X402_REQUEST_TIMEOUT=15
```

---

## 🔐 安全说明

⚠️ **重要提示**：

1. **本项目仅用于演示和研究**
2. 默认支付交易都是**模拟的**，不会产生真实链上交易
3. 不要在测试钱包中存入真实资金
4. 不要将私钥提交到代码仓库
5. `real_x402_request` 只做 dry-run 探测，不会签名或付款
6. 生产环境需要：
   - 真实的区块链交易验证
   - 安全的私钥管理（硬件钱包、KMS）
   - 完善的错误处理和重试机制
   - 交易金额和频率限制

---

## 📚 技术栈

**后端**
- Python 3.11+
- Flask - Web 框架
- Web3.py - 以太坊交互
- eth-account - 钱包和签名

**AI/LLM**
- Anthropic Claude API
- OpenAI-compatible API (Ollama / OMLX / MLX wrapper / API gateway)
- MCP (Model Context Protocol)

**开发工具**
- uv - Python 包管理
- python-dotenv - 环境变量管理

---

## 🛠️ 开发指南

### 添加新的付费服务

编辑 `mock-service/app.py`，添加新的端点：

```python
@app.route('/api/your-service', methods=['GET'])
def your_service():
    # 检查支付
    payment_proof = request.headers.get('X-Payment-Proof')
    
    if not payment_proof:
        # 返回 402
        response = jsonify({"error": "payment_required"})
        response.headers['X-Payment-Amount'] = '0.3'
        response.headers['X-Payment-Currency'] = 'USDC'
        # ... 其他 x402 headers
        return response, 402
    
    # 验证支付后返回内容
    return jsonify({"content": "Your paid content"})
```

### 调整支付策略

修改 `mcp-server/server.py` 中的 `handle_check_policy()` 逻辑。Agent 会通过 MCP 调用该工具，而不是在客户端内部直接判断策略：

```python
async def handle_check_policy(arguments: dict) -> list[TextContent]:
    amount = float(arguments["amount"])
    
    # 自定义策略
    if amount < 0.5:
        result = {"decision": "auto_approve"}
    elif amount < 2.0:
        result = {"decision": "request_approval"}
    else:
        result = {"decision": "reject", "reason": "exceeds limit"}

    return [TextContent(type="text", text=json.dumps(result))]
```

---

## 🔄 MCP Server 集成

当前版本中，`run_agent.py` 会启动 Agent 客户端，Agent 再通过 stdio 自动拉起并连接 `mcp-server/server.py`。Claude 只看到从 MCP Server 动态加载的工具定义，具体的 HTTP 请求、x402 检测、支付模拟、真实 x402 discovery、真实 x402 dry-run probe、余额查询和支付策略判断都在 MCP Server 中执行。

运行时链路：

1. Agent 初始化 MCP ClientSession
2. MCP Client 通过 stdio 启动 `mcp-server/server.py`
3. Agent 调用 `list_tools()` 加载工具 schema
4. Claude 发起 tool_use 后，Agent 将参数转发到 MCP Server 的 `call_tool()`
5. MCP Server 执行工具并把 JSON 结果返回给 Agent

### PaymentAdapter 设计

支付层采用适配器思路拆分：

- `MockPaymentAdapter`：当前默认适配器，生成模拟交易哈希，用于本地闭环演示。
- `RealX402DryRunAdapter`：真实 x402 探测适配器，只解析并展示 HTTP 402 payment requirements，不签名、不付款。
- 未来扩展：`CoinbaseX402Adapter` 或 `AgentCorePaymentAdapter`，用于接 Coinbase x402 client、CDP AgentKit 或 AWS AgentCore Payments。

真实支付接入顺序建议：

1. 先用 `discover_x402_services` 发现真实 x402 服务。
2. 再用 `real_x402_request` 请求一次真实 URL 并解析 402。
3. 确认预算、白名单、钱包网络和测试资金后，再实现真实签名适配器。
4. 优先使用 Base Sepolia 或小额 USDC 测试，确认 `402 -> sign -> retry` 流程。

参考 MCP 官方文档：https://github.com/anthropics/mcp

---

## 📖 相关资源

- **x402 协议**: https://docs.cdp.coinbase.com/x402/welcome
- **MCP 规范**: https://github.com/anthropics/mcp
- **Google AP2**: https://cloud.google.com/blog/products/ai-machine-learning/announcing-agents-to-payments-ap2-protocol
- **Cloudflare x402**: https://blog.cloudflare.com/x402/

---

## 🎓 毕业设计相关

本项目是毕业设计"基于 x402 协议与 MCP 架构的自主经济 AI Agent 设计与实现"的最小可执行 Demo。

### 核心创新点

1. **自主经济行为** - Agent 能独立完成"发现→评估→支付→获取"全流程
2. **标准化工具调用** - 使用 MCP 协议连接 AI 与工具层
3. **Web3 支付集成** - 展示加密货币在 AI Agent 场景的应用

### 后续扩展方向

- [x] 集成本地 LLM（OMLX Qwen3-Coder-30B / Qwen3.6-35B、Ollama Gemma 3）
- [x] Chainlit Web UI
- [x] Coinbase x402 Bazaar 真实服务发现
- [x] 真实 x402 URL dry-run 探测
- [ ] 真实区块链交易（Sepolia 测试网）
- [ ] 服务商白名单和黑名单
- [ ] 会话级预算管理
- [ ] 交易历史记录和审计
- [ ] 多币种支持（ETH, USDT, USDC）

---

## 📄 许可证

MIT License - 仅供学习和研究使用

---

## 👤 作者

牛稼豪 (202231235035)

---

## 🙏 致谢

- Anthropic - Claude API 和 MCP 协议
- Coinbase - x402 协议规范
- OKX - x402 实践指南

---

**⚡ 开始探索 AI Agent 的自主经济能力吧！**
