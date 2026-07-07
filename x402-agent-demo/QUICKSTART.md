# x402 Agent Demo - 快速使用指南

## 第一次运行（完整流程）

### 1. 安装依赖

```bash
cd x402-agent-demo
uv sync
```

### 2. 创建配置文件

```bash
uv run python setup.py
```

这将：
- 创建 `.env` 配置文件
- 启动时在内存中生成临时 Ethereum 密钥对，并提供 10 USDC 演示余额

### 3. 配置模型 API

编辑 `.env` 文件，选择一种模型接口。

**Anthropic / B.AI Claude-compatible：**

```env
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-api03-xxxxx
```

获取 API Key: https://console.anthropic.com/

**OpenAI-compatible 本地模型，例如 Ollama / OMLX / MLX wrapper：**

```env
LLM_PROVIDER=openai
OPENAI_BASE_URL=http://127.0.0.1:8000/v1
OPENAI_API_KEY=your_local_api_key
OPENAI_MODEL=your_local_model_id
```

如果本地 `/v1/models` 能返回模型列表，`OPENAI_MODEL` 可以先留空，Agent 会尝试自动选择第一个模型。

### 4. 测试系统

```bash
# 先启动 Mock 服务（保持运行）
uv run python run_mock_service.py
```

在另一个终端运行测试：

```bash
uv run python test_system.py
```

如果所有测试通过，继续下一步。

### 5. 启动 Agent

```bash
uv run python run_agent.py
```

也可以启动 Telegram 私聊版本：

```env
TELEGRAM_BOT_TOKEN=123456:your_bot_token
TELEGRAM_ALLOWED_USER_IDS=123456789
TELEGRAM_APPROVAL_TIMEOUT_SECONDS=300
```

```bash
uv run python telegram_bot.py
```

Telegram 版本使用 Long Polling，不需要公网地址。当前仅支持白名单私聊用户；
大额支付会显示“批准支付”和“拒绝支付”按钮。成功支付会更新当前会话余额和
支付记录；使用 `/new` 会重置对话与钱包账本。

## 使用示例

### 示例 1: 获取付费文章（自动支付）

```
👤 You: 帮我获取这篇文章 http://localhost:${MOCK_SERVICE_PORT:-5000}/api/article/quantum-2026

🤖 Agent 会：
1. 访问 URL
2. 检测到 402 付费墙 (0.5 USDC)
3. 检查支付策略（低于 1.0 自动批准）
4. 自动执行支付
5. 重新请求并返回内容
```

### 示例 2: 生成图片（自动支付）

```
👤 You: 用这个 API 生成一张赛博朋克风格的图片 http://localhost:${MOCK_SERVICE_PORT:-5000}/api/generate/image

请求体: {"prompt": "cyberpunk city"}

🤖 Agent 会自动支付 0.8 USDC 并返回生成的图片 URL
```

### 示例 3: 生成视频（需要确认）

```
👤 You: 生成一段 4K 风景视频 http://localhost:${MOCK_SERVICE_PORT:-5000}/api/generate/video

请求体: {"prompt": "mountain landscape"}

💰 PAYMENT APPROVAL REQUIRED
Amount: 5.0 USDC
Description: AI-Generated 10s 4K Video
Recipient: 0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb0

Approve payment? (yes/no): yes

✅ Payment executed
🤖 Agent: 视频已生成
```

### 示例 4: 发现真实 x402 服务（不付款）

```
👤 You: 搜索一些真实可用的 x402 加密数据 API

🤖 Agent 会：
1. 调用 discover_x402_services
2. 请求 Coinbase x402 Bazaar discovery/search
3. 返回真实服务列表和可探测 URL
4. 不签名、不付款
```

### 示例 5: 探测真实 x402 URL（dry-run）

```
👤 You: 用 real_x402_request 探测这个真实 x402 URL: https://example.com/paid-api

🤖 Agent 会：
1. 对 URL 请求一次
2. 如果返回 HTTP 402，解析 payment requirements
3. 展示金额、币种、网络、服务描述等信息
4. 不执行真实支付
```

## 常见问题

### Q: Mock 服务无法启动？

确保 `.env` 中配置的 `MOCK_SERVICE_PORT` 没有被占用：

```bash
# Windows
netstat -ano | findstr :5000

# 如果被占用，修改 .env 中的端口
MOCK_SERVICE_PORT=5001
```

### Q: Agent 不执行支付？

检查：
1. `.env` 中的 `MAX_AUTO_APPROVE_AMOUNT` 设置
2. 服务价格是否超过限额
3. API Key 是否正确配置

### Q: 如何调整自动支付额度？

编辑 `.env`:

```env
# 提高到 2.0 USDC
MAX_AUTO_APPROVE_AMOUNT=2.0
```

### Q: 如何添加新的付费服务？

编辑 `mock-service/app.py`，参考现有端点添加新的路由。

### Q: 真实 x402 工具会不会扣钱？

不会。当前 `discover_x402_services` 只做服务发现，`real_x402_request` 只做 dry-run 探测和 402 支付要求解析。真实签名和付款适配器还未启用。

### Q: 如何配置真实 x402 discovery？

编辑 `.env`:

```env
X402_BAZAAR_BASE_URL=https://api.cdp.coinbase.com/platform/v2/x402/discovery
ALLOW_REAL_X402_PAYMENT=false
X402_REQUEST_TIMEOUT=15
```

## 目录结构说明

```
x402-agent-demo/
├── .env                    # 你的配置（不要提交到 Git）
├── .env.example            # 配置模板
├── setup.py                # 初始化脚本
├── run_mock_service.py     # 启动 Mock 服务
├── run_agent.py            # 启动 Agent
├── telegram_bot.py         # Telegram 私聊入口
├── telegram_channel/       # Telegram 会话与审批适配
├── test_system.py          # 系统测试
│
├── mock-service/           # 模拟的 x402 付费服务
│   └── app.py             # Flask API
│
├── mcp-server/            # MCP 工具服务器（Agent 启动时通过 stdio 连接）
│   └── server.py          # MCP 工具实现，含 mock 支付与真实 x402 dry-run
│
└── agent-client/          # AI Agent 客户端
    └── agent.py           # Claude Agent 实现
```

## 下一步

1. **理解代码**: 阅读 `agent-client/agent.py` 了解 Agent 如何处理支付
2. **自定义服务**: 在 `mock-service/app.py` 添加你的付费 API
3. **调整策略**: 修改支付决策逻辑
4. **发现真实服务**: 使用 `discover_x402_services` 调 Coinbase x402 Bazaar
5. **探测真实 402**: 使用 `real_x402_request` 解析真实 payment requirements
6. **集成真实链**: 在 PaymentAdapter 中接 Coinbase x402 client 或 CDP AgentKit

## 注意事项

⚠️ **这是演示项目，所有支付都是模拟的！**

- 不会产生真实的区块链交易
- 真实 x402 工具目前只做 dry-run，不会签名或付款
- 演示钱包没有项目保存的私钥，不要用于真实资金
- 生产环境需要真实的交易验证

## 获取帮助

遇到问题？查看：
- `README.md` - 完整文档
- `CLAUDE.md` - 项目设计文档
- 或直接查看代码注释
