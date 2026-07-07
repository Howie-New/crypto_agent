import asyncio
import importlib.util
import json
import sys
import unittest
from contextlib import AsyncExitStack
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from web3 import Web3

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "agent-client"))

from agent import (  # noqa: E402
    AGENT_WALLET,
    LLMResponse,
    PaymentApprovalRequest,
    ToolCall,
    WalletState,
    X402Agent,
)
from telegram_bot import parse_allowed_user_ids  # noqa: E402
from telegram_channel.sessions import TelegramSessionManager  # noqa: E402
from telegram_channel.ui import TelegramApprovalHandler, split_message  # noqa: E402


class FakeLLM:
    name = "fake"

    def __init__(self, amount=5.0):
        self.responses = [
            LLMResponse(
                text="需要支付。",
                tool_calls=[
                    ToolCall(
                        id="payment-call",
                        name="web3_payment",
                        input={
                            "amount": amount,
                            "description": "Demo video",
                            "recipient": "0xabc",
                        },
                    )
                ],
                assistant_message={
                    "role": "assistant",
                    "content": "需要支付。",
                    "tool_calls": [
                        {
                            "id": "payment-call",
                            "type": "function",
                            "function": {
                                "name": "web3_payment",
                                "arguments": "{}",
                            },
                        }
                    ],
                },
            ),
            LLMResponse(
                text="处理完成。",
                tool_calls=[],
                assistant_message={"role": "assistant", "content": "处理完成。"},
            ),
        ]

    def chat(self, system_prompt, messages, tools):
        return self.responses.pop(0)


class FakeMcpSession:
    def __init__(self):
        self.calls = []

    async def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        content = type(
            "Content",
            (),
            {
                "type": "text",
                "text": json.dumps(
                    {
                        "status": "success",
                        "tx_hash": "0x123",
                    }
                ),
            },
        )()
        return type("Result", (), {"content": [content], "isError": False})()


def make_agent(approval_handler, amount=5.0):
    agent = object.__new__(X402Agent)
    agent.conversation_history = []
    agent.exit_stack = AsyncExitStack()
    agent.mcp_session = FakeMcpSession()
    agent.tools = []
    agent.llm = FakeLLM(amount=amount)
    agent.event_handler = None
    agent.approval_handler = approval_handler
    agent.wallet_state = WalletState()
    return agent


class AgentApprovalTests(unittest.IsolatedAsyncioTestCase):
    async def test_approved_payment_calls_mcp_tool(self):
        requests = []

        async def approve(request):
            requests.append(request)
            return True

        agent = make_agent(approve)
        result = await agent.chat("生成视频")

        self.assertEqual(result, "处理完成。")
        self.assertEqual(len(requests), 1)
        self.assertEqual(requests[0].amount, 5.0)
        self.assertEqual(len(agent.mcp_session.calls), 1)
        self.assertEqual(agent.mcp_session.calls[0][0], "web3_payment")
        self.assertEqual(agent.wallet_state.usdc_balance, 5)
        self.assertEqual(agent.wallet_state.payment_history[0]["status"], "success")

    async def test_rejected_payment_does_not_call_mcp_tool(self):
        async def reject(request):
            return False

        agent = make_agent(reject)
        result = await agent.chat("生成视频")

        self.assertEqual(result, "处理完成。")
        self.assertEqual(agent.mcp_session.calls, [])
        self.assertIn(
            "Payment rejected by user",
            agent.conversation_history[-2]["content"],
        )
        self.assertEqual(agent.wallet_state.usdc_balance, 10)
        self.assertEqual(agent.wallet_state.payment_history[0]["status"], "rejected")

    async def test_balance_tool_returns_updated_ledger(self):
        async def approve(request):
            return True

        agent = make_agent(approve)
        await agent.chat("生成视频")

        balance = await agent._call_mcp_tool("get_wallet_balance", {})

        self.assertEqual(balance["balances"]["USDC"], "5")
        self.assertEqual(len(balance["payment_history"]), 1)
        self.assertEqual(balance["payment_history"][0]["amount"], "5")

    async def test_insufficient_balance_blocks_payment(self):
        approval_called = False

        async def approve(request):
            nonlocal approval_called
            approval_called = True
            return True

        agent = make_agent(approve, amount=11.0)
        await agent.chat("生成高价视频")

        self.assertFalse(approval_called)
        self.assertEqual(agent.mcp_session.calls, [])
        self.assertEqual(agent.wallet_state.usdc_balance, 10)
        self.assertEqual(
            agent.wallet_state.payment_history[0]["status"],
            "insufficient_funds",
        )


class TelegramSessionTests(unittest.IsolatedAsyncioTestCase):
    async def test_sessions_are_isolated(self):
        sessions = TelegramSessionManager()
        first = sessions.get(100, 1)
        second = sessions.get(200, 2)

        first.conversation_history.append({"role": "user", "content": "first"})

        self.assertEqual(len(first.conversation_history), 1)
        self.assertEqual(second.conversation_history, [])

    async def test_reset_recreates_wallet_ledger(self):
        sessions = TelegramSessionManager()
        session = sessions.get(100, 1)
        session.wallet_state.usdc_balance = Decimal("9.5")
        session.wallet_state.payment_history.append({"status": "success"})

        reset = sessions.reset(100, 1)

        self.assertEqual(reset.wallet_state.usdc_balance, Decimal("10.0"))
        self.assertEqual(reset.wallet_state.payment_history, [])

    async def test_approval_is_scoped_and_consumed_once(self):
        sessions = TelegramSessionManager()
        request = PaymentApprovalRequest(
            id="a" * 32,
            amount=5.0,
            description="Demo",
            recipient="0xabc",
        )
        pending = sessions.begin_approval(100, 1, request)

        self.assertIsNone(
            sessions.resolve_approval(100, 2, request.id, approved=True)
        )
        resolved = sessions.resolve_approval(100, 1, request.id, approved=True)

        self.assertIs(resolved, pending)
        self.assertTrue(await pending.future)
        self.assertIsNone(
            sessions.resolve_approval(100, 1, request.id, approved=False)
        )

    async def test_expired_approval_is_removed(self):
        sessions = TelegramSessionManager()
        request = PaymentApprovalRequest(
            id="b" * 32,
            amount=5.0,
            description="Demo",
            recipient="0xabc",
        )
        pending = sessions.begin_approval(100, 1, request)

        expired = sessions.expire_approval(100, 1, request.id)

        self.assertIs(expired, pending)
        self.assertTrue(pending.future.cancelled())
        self.assertIsNone(sessions.get(100, 1).pending_approval)

    async def test_telegram_approval_resumes_after_button_decision(self):
        class FakeBot:
            def __init__(self):
                self.sent = []

            async def send_message(self, **kwargs):
                self.sent.append(kwargs)
                return type("Message", (), {"message_id": 42})()

            async def edit_message_text(self, **kwargs):
                return None

        sessions = TelegramSessionManager()
        bot = FakeBot()
        request = PaymentApprovalRequest(
            id="c" * 32,
            amount=5.0,
            description="Demo",
            recipient="0xabc",
        )
        handler = TelegramApprovalHandler(
            bot=bot,
            sessions=sessions,
            chat_id=100,
            user_id=1,
            timeout_seconds=5,
        )

        approval_task = asyncio.create_task(handler(request))
        await asyncio.sleep(0)
        sessions.resolve_approval(100, 1, request.id, approved=True)

        self.assertTrue(await approval_task)
        self.assertEqual(len(bot.sent), 1)
        self.assertIn("批准支付", str(bot.sent[0]["reply_markup"]))


class TelegramHelpersTests(unittest.TestCase):
    def test_agent_uses_safe_demo_wallet(self):
        self.assertTrue(Web3.is_address(AGENT_WALLET))
        self.assertNotEqual(
            AGENT_WALLET,
            "0x1111111111111111111111111111111111111111",
        )

    def test_allowed_user_ids_are_numeric(self):
        self.assertEqual(parse_allowed_user_ids("123, 456"), {123, 456})
        with self.assertRaises(ValueError):
            parse_allowed_user_ids("123,username")

    def test_long_messages_are_split_without_data_loss(self):
        text = ("第一段内容。\n\n" * 700).strip()
        chunks = split_message(text, limit=100)

        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk) <= 100 for chunk in chunks))
        self.assertEqual("\n\n".join(chunks), text)


class DemoWalletTests(unittest.IsolatedAsyncioTestCase):
    async def test_mcp_balance_defaults_to_ten_usdc(self):
        server_path = PROJECT_ROOT / "mcp-server" / "server.py"
        with patch.dict(
            "os.environ",
            {"DEMO_WALLET_ADDRESS": AGENT_WALLET},
        ):
            spec = importlib.util.spec_from_file_location(
                "demo_mcp_server",
                server_path,
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

        response = await module.handle_get_balance({})
        payload = json.loads(response[0].text)

        self.assertEqual(payload["address"], AGENT_WALLET)
        self.assertEqual(payload["balances"]["USDC"], "10.0")
        self.assertNotIn("note", payload)

    async def test_discovery_results_are_compact_and_limited(self):
        server_path = PROJECT_ROOT / "mcp-server" / "server.py"
        spec = importlib.util.spec_from_file_location(
            "discovery_mcp_server",
            server_path,
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        verbose_item = {
            "serviceName": "Example Service",
            "resource": "https://example.com/resource",
            "description": "Example description",
            "type": "http",
            "x402Version": 2,
            "accepts": [
                {
                    "amount": "10000",
                    "asset": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
                    "network": "eip155:8453",
                    "scheme": "exact",
                    "extra": {"name": "USD Coin"},
                }
            ],
            "extensions": {"bazaar": {"schema": {"large": "x" * 10000}}},
        }
        payload = {
            "items": [verbose_item for _ in range(20)],
            "pagination": {"total": 23286},
        }

        services, total = module.compact_discovery_results(payload, limit=5)

        self.assertEqual(len(services), 5)
        self.assertEqual(total, 23286)
        self.assertNotIn("extensions", services[0])
        self.assertEqual(services[0]["payment_options"][0]["amount"], "0.01")
        self.assertEqual(services[0]["payment_options"][0]["network"], "Base")
        self.assertLess(len(json.dumps(services)), 5000)


if __name__ == "__main__":
    unittest.main()
