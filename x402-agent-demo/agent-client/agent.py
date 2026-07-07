"""
AI Agent Client with x402 Payment Capability
Uses Anthropic Claude API with MCP tools
"""

import asyncio
import json
import os
import re
import sys
import uuid
from dataclasses import dataclass, field
from contextlib import AsyncExitStack
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Awaitable, Callable

import requests
from anthropic import Anthropic
from dotenv import load_dotenv
from eth_account import Account
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Load environment variables
load_dotenv(PROJECT_ROOT / ".env")

# Agent configuration
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "anthropic").strip().lower()
MAX_AUTO_APPROVE_AMOUNT = float(os.getenv("MAX_AUTO_APPROVE_AMOUNT", "1.0"))
MAX_TOOL_ROUNDS = int(os.getenv("MAX_TOOL_ROUNDS", "8"))
DEMO_WALLET_ACCOUNT = Account.create()
AGENT_WALLET = DEMO_WALLET_ACCOUNT.address


@dataclass
class ToolCall:
    """Provider-neutral tool call."""

    id: str
    name: str
    input: dict


@dataclass
class LLMResponse:
    """Provider-neutral LLM response."""

    text: str
    tool_calls: list[ToolCall]
    assistant_message: dict


@dataclass
class AgentEvent:
    """Structured event emitted by the agent for CLI/Web UI surfaces."""

    type: str
    payload: dict


AgentEventHandler = Callable[[AgentEvent], Awaitable[None]]


@dataclass(frozen=True)
class PaymentApprovalRequest:
    """Provider-neutral request for explicit user approval."""

    id: str
    amount: float
    description: str
    recipient: str


PaymentApprovalHandler = Callable[[PaymentApprovalRequest], Awaitable[bool]]


def decimal_text(value: Decimal) -> str:
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") or "0"


@dataclass
class WalletState:
    """In-memory wallet balance and payment ledger for one UI session."""

    address: str = AGENT_WALLET
    eth_balance: Decimal = field(
        default_factory=lambda: Decimal(os.getenv("DEMO_ETH_BALANCE", "0.1"))
    )
    usdc_balance: Decimal = field(
        default_factory=lambda: Decimal(os.getenv("DEMO_USDC_BALANCE", "10.0"))
    )
    payment_history: list[dict] = field(default_factory=list)

    def can_pay(self, amount: float, currency: str) -> bool:
        return currency.upper() == "USDC" and self.usdc_balance >= Decimal(str(amount))

    def record_payment(
        self,
        *,
        amount: float,
        currency: str,
        recipient: str,
        description: str,
        status: str,
        tx_hash: str | None = None,
    ) -> None:
        amount_value = Decimal(str(amount))
        if status == "success" and currency.upper() == "USDC":
            self.usdc_balance -= amount_value

        self.payment_history.append(
            {
                "id": uuid.uuid4().hex,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "description": description,
                "recipient": recipient,
                "amount": decimal_text(amount_value),
                "currency": currency.upper(),
                "status": status,
                "tx_hash": tx_hash,
                "balance_after": {
                    "ETH": decimal_text(self.eth_balance),
                    "USDC": decimal_text(self.usdc_balance),
                },
            }
        )

    def snapshot(self) -> dict:
        return {
            "address": self.address,
            "balances": {
                "ETH": decimal_text(self.eth_balance),
                "USDC": decimal_text(self.usdc_balance),
            },
            "payment_history": list(self.payment_history),
        }


class AnthropicProvider:
    """Anthropic Messages API provider."""

    name = "anthropic"

    def __init__(self):
        api_key = os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN")
        base_url = os.getenv("ANTHROPIC_BASE_URL")
        if not api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY or ANTHROPIC_AUTH_TOKEN is required for Anthropic provider"
            )

        kwargs = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        self.client = Anthropic(**kwargs)
        self.model = os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-20241022")

    def prepare_tools(self, tools: list[dict]) -> list[dict]:
        return tools

    def _convert_messages(self, messages: list[dict]) -> list[dict]:
        converted = []
        for message in messages:
            role = message["role"]
            if role == "tool":
                converted.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": message["tool_call_id"],
                                "content": message["content"],
                            }
                        ],
                    }
                )
            elif role == "assistant" and message.get("tool_calls"):
                content = []
                if message.get("content"):
                    content.append({"type": "text", "text": message["content"]})
                for call in message["tool_calls"]:
                    content.append(
                        {
                            "type": "tool_use",
                            "id": call["id"],
                            "name": call["function"]["name"],
                            "input": json.loads(call["function"]["arguments"]),
                        }
                    )
                converted.append({"role": "assistant", "content": content})
            else:
                converted.append({"role": role, "content": message.get("content", "")})
        return converted

    def chat(self, system_prompt: str, messages: list[dict], tools: list[dict]) -> LLMResponse:
        response = self.client.messages.create(
            model=self.model,
            max_tokens=4096,
            system=system_prompt,
            tools=self.prepare_tools(tools),
            messages=self._convert_messages(messages),
        )

        text_parts = []
        tool_calls = []
        openai_tool_calls = []

        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_input = block.input or {}
                tool_calls.append(ToolCall(block.id, block.name, tool_input))
                openai_tool_calls.append(
                    {
                        "id": block.id,
                        "type": "function",
                        "function": {
                            "name": block.name,
                            "arguments": json.dumps(tool_input),
                        },
                    }
                )

        text = "".join(text_parts)
        return LLMResponse(
            text=text,
            tool_calls=tool_calls,
            assistant_message={
                "role": "assistant",
                "content": text,
                "tool_calls": openai_tool_calls,
            },
        )


class OpenAICompatibleProvider:
    """OpenAI-compatible Chat Completions provider for Ollama/OMLX/B.AI/etc."""

    name = "openai"

    def __init__(self):
        self.base_url = os.getenv("OPENAI_BASE_URL", "http://127.0.0.1:8000/v1").rstrip("/")
        self.api_key = os.getenv("OPENAI_API_KEY", "local")
        self.model = os.getenv("OPENAI_MODEL") or self._detect_model()
        self.timeout = float(os.getenv("OPENAI_REQUEST_TIMEOUT", "120"))
        self.max_tokens = int(os.getenv("OPENAI_MAX_TOKENS", "1024"))

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _detect_model(self) -> str:
        try:
            response = requests.get(
                f"{self.base_url}/models",
                headers=self._headers(),
                timeout=5,
            )
            response.raise_for_status()
            models = response.json().get("data", [])
            if models:
                return models[0]["id"]
        except Exception:
            pass
        return "local-model"

    def prepare_tools(self, tools: list[dict]) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool.get("description", ""),
                    "parameters": tool.get("input_schema")
                    or {"type": "object", "properties": {}},
                },
            }
            for tool in tools
        ]

    def _normalize_model_text(self, content: str) -> str:
        return content.replace("\u0120", " ").replace("\u010A", "\n")

    def _extract_json_payload(self, content: str) -> str:
        normalized = self._normalize_model_text(content)
        has_tool_marker = "[TOOL_CALLS]" in normalized
        if has_tool_marker:
            normalized = normalized.split("[TOOL_CALLS]", 1)[1]

        stripped = normalized.strip()
        if stripped.startswith("```"):
            lines = stripped.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            stripped = "\n".join(lines).strip()

        if stripped.startswith("{") and stripped.endswith("}"):
            return stripped

        start = stripped.find("{")
        end = stripped.rfind("}")
        if not has_tool_marker and start != -1 and end != -1 and end > start:
            return stripped[start : end + 1]
        return stripped

    def _parse_text_tool_calls(self, payload: str) -> list[ToolCall]:
        """Parse simple local-model text formats such as `tool_name: {}`."""
        calls = []
        for line in payload.splitlines():
            line = line.strip()
            if not line or line.lower().startswith("tool_calls"):
                continue

            match = re.match(r"^(?P<name>[A-Za-z_][\w-]*)\s*:\s*(?P<args>\{.*\})\s*$", line)
            if not match:
                continue

            try:
                arguments = json.loads(match.group("args"))
            except json.JSONDecodeError:
                arguments = {}

            calls.append(
                ToolCall(f"text_tool_{len(calls) + 1}", match.group("name"), arguments)
            )

        return calls

    def _parse_json_tool_calls(self, content: str) -> list[ToolCall]:
        """Fallback for local models that emit JSON instead of native tool calls."""
        payload = self._extract_json_payload(content)
        try:
            parsed = json.loads(payload)
        except Exception:
            return self._parse_text_tool_calls(payload)

        raw_calls = parsed.get("tool_calls")
        if raw_calls is None and parsed.get("tool"):
            raw_calls = [
                {
                    "name": parsed["tool"],
                    "arguments": parsed.get("arguments", {}),
                }
            ]
        if not isinstance(raw_calls, list):
            return []

        calls = []
        for idx, call in enumerate(raw_calls, 1):
            name = call.get("name") or call.get("tool")
            arguments = call.get("arguments") or call.get("input") or {}
            if isinstance(arguments, str):
                try:
                    arguments = json.loads(arguments)
                except json.JSONDecodeError:
                    arguments = {}
            if name:
                calls.append(ToolCall(f"json_tool_{idx}", name, arguments))
        return calls

    def chat(self, system_prompt: str, messages: list[dict], tools: list[dict]) -> LLMResponse:
        request_messages = [{"role": "system", "content": system_prompt}, *messages]
        payload = {
            "model": self.model,
            "messages": request_messages,
            "tools": self.prepare_tools(tools),
            "tool_choice": "auto",
            "temperature": 0.2,
            "max_tokens": self.max_tokens,
        }
        response = requests.post(
            f"{self.base_url}/chat/completions",
            headers=self._headers(),
            json=payload,
            timeout=self.timeout,
        )
        response.raise_for_status()
        data = response.json()
        message = data["choices"][0]["message"]
        text = self._normalize_model_text(message.get("content") or "").strip()

        tool_calls = []
        openai_tool_calls = []
        for call in message.get("tool_calls") or []:
            function = call.get("function", {})
            arguments = function.get("arguments") or "{}"
            try:
                tool_input = json.loads(arguments)
            except json.JSONDecodeError:
                tool_input = {}
            tool_calls.append(
                ToolCall(call.get("id", function.get("name", "tool_call")), function.get("name"), tool_input)
            )
            openai_tool_calls.append(call)

        if not tool_calls and text:
            tool_calls = self._parse_json_tool_calls(text)
            openai_tool_calls = [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {
                        "name": call.name,
                        "arguments": json.dumps(call.input),
                    },
                }
                for call in tool_calls
            ]

        assistant_message = {"role": "assistant", "content": text}
        if openai_tool_calls:
            assistant_message["tool_calls"] = openai_tool_calls

        return LLMResponse(text=text, tool_calls=tool_calls, assistant_message=assistant_message)


def create_llm_provider():
    if LLM_PROVIDER in ("openai", "ollama", "omlx", "mlx"):
        return OpenAICompatibleProvider()
    if LLM_PROVIDER in ("anthropic", "claude"):
        return AnthropicProvider()
    raise RuntimeError(f"Unsupported LLM_PROVIDER: {LLM_PROVIDER}")


def get_user_approval(request: PaymentApprovalRequest) -> bool:
    """Request payment approval from the CLI."""
    print("\n" + "=" * 60)
    print("💰 PAYMENT APPROVAL REQUIRED")
    print("=" * 60)
    print(f"Amount: {request.amount} USDC")
    print(f"Description: {request.description}")
    print(f"Recipient: {request.recipient}")
    print(f"Max auto-approve limit: {MAX_AUTO_APPROVE_AMOUNT} USDC")
    print("=" * 60)

    while True:
        response = input("\nApprove payment? (yes/no): ").strip().lower()
        if response in ["yes", "y"]:
            return True
        elif response in ["no", "n"]:
            return False
        else:
            print("Please enter 'yes' or 'no'")


async def cli_payment_approval(request: PaymentApprovalRequest) -> bool:
    """Run the blocking CLI prompt without blocking the event loop."""
    return await asyncio.to_thread(get_user_approval, request)


class X402Agent:
    """AI Agent with x402 payment capability"""

    def __init__(
        self,
        event_handler: AgentEventHandler | None = None,
        approval_handler: PaymentApprovalHandler | None = None,
        wallet_state: WalletState | None = None,
    ):
        self.conversation_history = []
        self.exit_stack = AsyncExitStack()
        self.mcp_session = None
        self.tools = []
        self.llm = create_llm_provider()
        self.event_handler = event_handler
        self.approval_handler = approval_handler
        self.wallet_state = wallet_state or WalletState()

    async def _emit(self, event_type: str, payload: dict):
        if self.event_handler:
            await self.event_handler(AgentEvent(event_type, payload))

    async def connect_mcp_server(self):
        """Start the MCP server process and load its tool definitions."""
        server_script = PROJECT_ROOT / "mcp-server" / "server.py"

        env = os.environ.copy()
        env.setdefault("UV_CACHE_DIR", "/tmp/uv-cache")
        env["DEMO_WALLET_ADDRESS"] = AGENT_WALLET
        server_params = StdioServerParameters(
            command="uv",
            args=[
                "--project",
                str(PROJECT_ROOT),
                "--cache-dir",
                env["UV_CACHE_DIR"],
                "run",
                "python",
                str(server_script),
            ],
            env=env,
        )

        stdio_transport = await self.exit_stack.enter_async_context(
            stdio_client(server_params)
        )
        read_stream, write_stream = stdio_transport

        self.mcp_session = await self.exit_stack.enter_async_context(
            ClientSession(read_stream, write_stream)
        )
        await self.mcp_session.initialize()

        tools_result = await self.mcp_session.list_tools()
        self.tools = [self._to_provider_tool(tool) for tool in tools_result.tools]

        print(f"\n🔌 Connected to MCP server: {server_script}")
        print("🧰 MCP tools loaded: " + ", ".join(tool["name"] for tool in self.tools))
        print(f"🧠 LLM provider: {self.llm.name}")
        if hasattr(self.llm, "base_url"):
            print(f"🌐 LLM base URL: {self.llm.base_url}")
        if hasattr(self.llm, "model"):
            print(f"📦 LLM model: {self.llm.model}")
        await self._emit(
            "connected",
            {
                "server": str(server_script),
                "tools": [tool["name"] for tool in self.tools],
                "provider": self.llm.name,
                "base_url": getattr(self.llm, "base_url", None),
                "model": getattr(self.llm, "model", None),
            },
        )

    async def close(self):
        """Stop the MCP server process and release streams."""
        await self.exit_stack.aclose()

    def _to_provider_tool(self, tool) -> dict:
        """Convert an MCP Tool object to a provider-neutral tool schema."""
        input_schema = getattr(tool, "inputSchema", None)
        if input_schema is None and isinstance(tool, dict):
            input_schema = tool.get("inputSchema", {})

        return {
            "name": getattr(tool, "name", None)
            if not isinstance(tool, dict)
            else tool["name"],
            "description": getattr(tool, "description", "")
            if not isinstance(tool, dict)
            else tool.get("description", ""),
            "input_schema": input_schema or {"type": "object", "properties": {}},
        }

    def _parse_mcp_result(self, result) -> dict:
        """Return a JSON-friendly payload from an MCP tool result."""
        content_blocks = []

        for content in getattr(result, "content", []):
            if getattr(content, "type", None) == "text":
                text = content.text
                try:
                    return json.loads(text)
                except json.JSONDecodeError:
                    content_blocks.append({"type": "text", "text": text})
            else:
                content_blocks.append(
                    {
                        "type": getattr(content, "type", "unknown"),
                        "data": str(content),
                    }
                )

        parsed = {"content": content_blocks}
        if getattr(result, "isError", False):
            parsed["error"] = True
        return parsed

    async def _call_mcp_tool(self, tool_name: str, tool_input: dict) -> dict:
        """Call a tool through the MCP session."""
        if tool_name == "get_wallet_balance":
            return self.wallet_state.snapshot()
        if self.mcp_session is None:
            raise RuntimeError("MCP server is not connected")

        result = await self.mcp_session.call_tool(tool_name, tool_input)
        parsed = self._parse_mcp_result(result)
        if (
            tool_name == "web3_payment"
            and parsed.get("status") == "success"
        ):
            self.wallet_state.record_payment(
                amount=float(tool_input["amount"]),
                currency=tool_input.get("currency", "USDC"),
                recipient=tool_input["recipient"],
                description=tool_input.get("description", "Payment"),
                status="success",
                tx_hash=parsed.get("tx_hash"),
            )
        return parsed

    def _create_system_prompt(self) -> str:
        """Create system prompt for the agent"""
        return """You are an AI assistant with the ability to autonomously access paid content and services using cryptocurrency payments.

You have access to the following tools:
1. http_request - Make HTTP requests to any URL. This tool will automatically detect if a service requires payment (HTTP 402 status).
2. web3_payment - Execute cryptocurrency payments to unlock paid content.
3. get_wallet_balance - Check current wallet balances and session payment history.
4. check_payment_policy - Check if a payment requires user approval.
5. discover_x402_services - Discover real x402 services from Coinbase x402 Bazaar. This does not pay.
6. real_x402_request - Probe a real x402 URL and parse payment requirements. This is dry-run only.

If your model runtime cannot emit native tool calls, respond with JSON only:
{{"tool": "tool_name", "arguments": {{...}}}}
or
{{"tool_calls": [{{"name": "tool_name", "arguments": {{...}}}}]}}

Payment Policy:
- Payments under {max_auto} USDC are automatically approved
- Payments above {max_auto} USDC require user confirmation
- Always check payment policy before making payments

When you encounter a 402 Payment Required response:
1. Parse the payment information (amount, recipient, description)
2. Check the payment policy to see if approval is needed
3. If auto-approved: proceed with payment automatically
4. If approval needed: explain the situation and ask the user
5. After payment, retry the request with payment proof

Always be transparent about payments and explain what you're paying for.
For real_x402_request results, do not claim a real payment was made. Treat real x402 payment requirements as inspection output until a real payment adapter is explicitly enabled.

Your wallet address: {wallet}
""".format(max_auto=MAX_AUTO_APPROVE_AMOUNT, wallet=AGENT_WALLET)

    async def chat(self, user_message: str) -> str:
        """Send a message and get response"""

        # Add user message to history
        self.conversation_history.append({"role": "user", "content": user_message})

        response = self.llm.chat(
            self._create_system_prompt(), self.conversation_history, self.tools
        )

        # Process response
        tool_round = 0
        while response.tool_calls:
            tool_round += 1
            if tool_round > MAX_TOOL_ROUNDS:
                warning = (
                    f"Stopped after {MAX_TOOL_ROUNDS} tool rounds to avoid an infinite loop."
                )
                self.conversation_history.append(
                    {"role": "assistant", "content": warning}
                )
                return warning

            tool_results = []
            if response.text:
                print(f"\n🤖 Agent: {response.text}")
                await self._emit("assistant_message", {"content": response.text})

            self.conversation_history.append(response.assistant_message)

            for tool_call in response.tool_calls:
                tool_name = tool_call.name
                tool_input = tool_call.input

                print(f"\n🔧 Tool Call: {tool_name}")
                print(f"   Input: {json.dumps(tool_input, indent=2)}")
                await self._emit(
                    "tool_start",
                    {
                        "id": tool_call.id,
                        "name": tool_name,
                        "input": tool_input,
                    },
                )

                if tool_name == "web3_payment":
                    amount = float(tool_input["amount"])
                    currency = tool_input.get("currency", "USDC")
                    description = tool_input.get("description", "Payment")
                    recipient = tool_input["recipient"]
                    if not self.wallet_state.can_pay(amount, currency):
                        self.wallet_state.record_payment(
                            amount=amount,
                            currency=currency,
                            recipient=recipient,
                            description=description,
                            status="insufficient_funds",
                        )
                        tool_result = {
                            "status": "error",
                            "error": "Insufficient wallet balance",
                            "balances": self.wallet_state.snapshot()["balances"],
                        }
                        await self._emit(
                            "tool_result",
                            {
                                "id": tool_call.id,
                                "name": tool_name,
                                "result": tool_result,
                            },
                        )
                        tool_results.append(
                            {
                                "role": "tool",
                                "tool_call_id": tool_call.id,
                                "content": json.dumps(tool_result),
                            }
                        )
                        continue

                    if amount > MAX_AUTO_APPROVE_AMOUNT:
                        approval_request = PaymentApprovalRequest(
                            id=uuid.uuid4().hex,
                            amount=amount,
                            description=description,
                            recipient=recipient,
                        )
                        await self._emit(
                            "payment_approval_required",
                            {
                                "id": approval_request.id,
                                "amount": approval_request.amount,
                                "description": approval_request.description,
                                "recipient": approval_request.recipient,
                            },
                        )
                        approved = False
                        if self.approval_handler is not None:
                            approved = await self.approval_handler(approval_request)
                        await self._emit(
                            "payment_approval_resolved",
                            {
                                "id": approval_request.id,
                                "approved": approved,
                            },
                        )
                        if not approved:
                            self.wallet_state.record_payment(
                                amount=amount,
                                currency=currency,
                                recipient=recipient,
                                description=description,
                                status="rejected",
                            )
                            tool_result = {
                                "status": "rejected",
                                "error": "Payment rejected by user",
                            }
                            await self._emit(
                                "tool_result",
                                {
                                    "id": tool_call.id,
                                    "name": tool_name,
                                    "result": tool_result,
                                },
                            )
                            tool_results.append(
                                {
                                    "role": "tool",
                                    "tool_call_id": tool_call.id,
                                    "content": json.dumps(tool_result),
                                }
                            )
                            continue

                tool_result = await self._call_mcp_tool(tool_name, tool_input)
                print(f"   Result: {json.dumps(tool_result, indent=2)}")
                await self._emit(
                    "tool_result",
                    {
                        "id": tool_call.id,
                        "name": tool_name,
                        "result": tool_result,
                    },
                )

                tool_results.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": json.dumps(tool_result),
                    }
                )

            self.conversation_history.extend(tool_results)

            response = self.llm.chat(
                self._create_system_prompt(), self.conversation_history, self.tools
            )

        final_text = response.text
        self.conversation_history.append(response.assistant_message)
        await self._emit("final_message", {"content": final_text})

        return final_text


async def run_agent():
    """Run the agent"""
    print("=" * 60)
    print("🤖 x402 AI Agent - Autonomous Economic Agent")
    print("=" * 60)
    print(f"Wallet: {AGENT_WALLET}")
    print(f"Auto-approve limit: {MAX_AUTO_APPROVE_AMOUNT} USDC")
    print("\nThe agent can autonomously pay for content and services.")
    print(
        f"Try: 'Get the premium article at http://localhost:{os.getenv('MOCK_SERVICE_PORT', '5000')}/api/article/quantum-2026'"
    )
    print("=" * 60)

    try:
        agent = X402Agent(approval_handler=cli_payment_approval)
    except Exception as e:
        print(f"\n❌ Error initializing LLM provider: {e}")
        sys.exit(1)

    try:
        await agent.connect_mcp_server()

        print("\nType 'quit' to exit\n")

        while True:
            try:
                user_input = input("\n👤 You: ").strip()

                if user_input.lower() in ["quit", "exit", "q"]:
                    print("\n👋 Goodbye!")
                    break

                if not user_input:
                    continue

                response = await agent.chat(user_input)
                print(f"\n🤖 Agent: {response}")

            except KeyboardInterrupt:
                print("\n\n👋 Goodbye!")
                break
            except Exception as e:
                print(f"\n❌ Error: {e}")
    finally:
        await agent.close()


def main():
    asyncio.run(run_agent())


if __name__ == "__main__":
    main()
