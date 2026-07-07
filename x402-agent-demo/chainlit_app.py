"""
Chainlit Web UI for the x402 Agent demo.

Run with:
uv run chainlit run chainlit_app.py --host 127.0.0.1 --port 7860
"""

import json
import sys
from pathlib import Path

import chainlit as cl

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT / "agent-client"))

from agent import (  # noqa: E402
    AgentEvent,
    PaymentApprovalRequest,
    WalletState,
    X402Agent,
)


def pretty_json(payload: dict) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=False)


class ChainlitEventSink:
    """Render agent events as Chainlit messages and tool steps."""

    def __init__(self):
        self.steps = {}

    async def __call__(self, event: AgentEvent):
        payload = event.payload

        if event.type == "connected":
            tools = ", ".join(payload["tools"])
            lines = [
                "**x402 Agent 已连接**",
                f"- 模型提供方：`{payload['provider']}`",
                f"- 模型：`{payload.get('model') or 'unknown'}`",
                f"- MCP Server：`{payload['server']}`",
                f"- MCP 工具：{tools}",
            ]
            if payload.get("base_url"):
                lines.insert(2, f"- Base URL：`{payload['base_url']}`")
            await cl.Message(content="\n".join(lines)).send()
            return

        if event.type == "assistant_message" and payload.get("content"):
            async with cl.Step(
                name="Agent decision",
                type="llm",
                language="markdown",
                default_open=False,
                icon="brain",
            ) as step:
                step.output = payload["content"]
            return

        if event.type == "tool_start":
            step = cl.Step(
                name=f"Tool: {payload['name']}",
                type="tool",
                show_input="json",
                language="json",
                default_open=True,
                icon="wrench",
            )
            step.input = pretty_json(payload.get("input") or {})
            step.output = "Running..."
            await step.send()
            self.steps[payload["id"]] = step
            return

        if event.type == "tool_result":
            step = self.steps.pop(payload["id"], None)
            if step is None:
                step = cl.Step(
                    name=f"Tool: {payload['name']}",
                    type="tool",
                    show_input="json",
                    language="json",
                    default_open=True,
                    icon="wrench",
                )
                step.input = "{}"
                await step.send()
            step.output = pretty_json(payload.get("result") or {})
            await step.update()


async def request_payment_approval(request: PaymentApprovalRequest) -> bool:
    response = await cl.AskActionMessage(
        content=(
            "需要确认一笔大额支付：\n\n"
            f"- 金额：`{request.amount} USDC`\n"
            f"- 用途：{request.description}\n"
            f"- 收款地址：`{request.recipient}`"
        ),
        actions=[
            cl.Action(
                name="approve_payment",
                payload={"decision": "approve"},
                label="批准支付",
            ),
            cl.Action(
                name="reject_payment",
                payload={"decision": "reject"},
                label="拒绝支付",
            ),
        ],
        timeout=300,
    ).send()
    return bool(response and response["payload"].get("decision") == "approve")


async def create_agent(wallet_state: WalletState) -> X402Agent:
    sink = ChainlitEventSink()
    agent = X402Agent(
        event_handler=sink,
        approval_handler=request_payment_approval,
        wallet_state=wallet_state,
    )
    await agent.connect_mcp_server()
    return agent


def get_history() -> list[dict]:
    return cl.user_session.get("conversation_history") or []


def get_wallet_state() -> WalletState:
    wallet_state = cl.user_session.get("wallet_state")
    if wallet_state is None:
        wallet_state = WalletState()
        cl.user_session.set("wallet_state", wallet_state)
    return wallet_state


@cl.set_starters
async def starters():
    return [
        cl.Starter(
            label="查询钱包余额",
            message="请调用 get_wallet_balance 工具查询钱包余额，并用中文摘要说明。",
        ),
        cl.Starter(
            label="访问付费文章",
            message=(
                "请访问本地付费文章 http://127.0.0.1:5050/api/article/quantum-2026，"
                "展示 402 支付要求，并在符合策略时完成模拟支付。"
            ),
        ),
        cl.Starter(
            label="发现真实 x402 服务",
            message="请调用 discover_x402_services 搜索真实 x402 服务，limit=5。",
        ),
    ]


@cl.on_chat_start
async def on_chat_start():
    cl.user_session.set("conversation_history", [])
    cl.user_session.set("wallet_state", WalletState())
    await cl.Message(
        content=(
            "x402 Agent WebUI 已就绪。每次请求会临时连接 MCP Server，"
            "并在同一任务内关闭连接，以保证 Chainlit 展示稳定。"
        )
    ).send()


@cl.on_message
async def on_message(message: cl.Message):
    async with cl.Step(
        name="Agent run",
        type="run",
        show_input=True,
        language="markdown",
        default_open=False,
        icon="bot",
    ) as step:
        step.input = message.content
        agent = await create_agent(get_wallet_state())
        agent.conversation_history = get_history()
        try:
            result = await agent.chat(message.content)
            cl.user_session.set("conversation_history", agent.conversation_history)
            step.output = result or "Done"
        finally:
            await agent.close()

    await cl.Message(content=result or "已完成，但模型没有返回最终文本。").send()


@cl.on_chat_end
async def on_chat_end():
    cl.user_session.set("conversation_history", [])
