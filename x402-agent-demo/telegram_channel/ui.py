import asyncio

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest, TelegramError
from telegram.ext import ExtBot

from agent import AgentEvent, PaymentApprovalRequest
from telegram_channel.sessions import TelegramSessionManager


TELEGRAM_TEXT_LIMIT = 3500


def split_message(text: str, limit: int = TELEGRAM_TEXT_LIMIT) -> list[str]:
    """Split long text while preferring paragraph and line boundaries."""
    text = text.strip()
    if not text:
        return []

    chunks: list[str] = []
    remaining = text
    while len(remaining) > limit:
        split_at = remaining.rfind("\n\n", 0, limit)
        if split_at < limit // 2:
            split_at = remaining.rfind("\n", 0, limit)
        if split_at < limit // 2:
            split_at = remaining.rfind(" ", 0, limit)
        if split_at < limit // 2:
            split_at = limit
        chunks.append(remaining[:split_at].strip())
        remaining = remaining[split_at:].strip()
    if remaining:
        chunks.append(remaining)
    return chunks


async def send_long_message(bot: ExtBot, chat_id: int, text: str) -> None:
    for chunk in split_message(text):
        await bot.send_message(chat_id=chat_id, text=chunk)


class TelegramEventSink:
    """Render agent events as compact Telegram status messages."""

    def __init__(self, bot: ExtBot, chat_id: int):
        self.bot = bot
        self.chat_id = chat_id
        self.tool_messages: dict[str, int] = {}

    async def __call__(self, event: AgentEvent) -> None:
        payload = event.payload

        if event.type == "assistant_message" and payload.get("content"):
            await send_long_message(self.bot, self.chat_id, payload["content"])
            return

        if event.type == "tool_start":
            message = await self.bot.send_message(
                chat_id=self.chat_id,
                text=f"正在调用工具：{payload['name']}",
            )
            self.tool_messages[payload["id"]] = message.message_id
            return

        if event.type == "tool_result":
            message_id = self.tool_messages.pop(payload["id"], None)
            if message_id is None:
                return
            result = payload.get("result") or {}
            status = "执行失败" if result.get("error") else "执行完成"
            try:
                await self.bot.edit_message_text(
                    chat_id=self.chat_id,
                    message_id=message_id,
                    text=f"工具{status}：{payload['name']}",
                )
            except BadRequest:
                pass


class TelegramApprovalHandler:
    """Ask for payment approval using a one-time inline keyboard."""

    def __init__(
        self,
        bot: ExtBot,
        sessions: TelegramSessionManager,
        chat_id: int,
        user_id: int,
        timeout_seconds: int,
    ):
        self.bot = bot
        self.sessions = sessions
        self.chat_id = chat_id
        self.user_id = user_id
        self.timeout_seconds = timeout_seconds

    async def __call__(self, request: PaymentApprovalRequest) -> bool:
        pending = self.sessions.begin_approval(
            self.chat_id,
            self.user_id,
            request,
        )
        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "批准支付",
                        callback_data=f"pay:{request.id}:approve",
                    ),
                    InlineKeyboardButton(
                        "拒绝支付",
                        callback_data=f"pay:{request.id}:reject",
                    ),
                ]
            ]
        )
        try:
            message = await self.bot.send_message(
                chat_id=self.chat_id,
                text=(
                    "需要确认一笔大额支付\n\n"
                    f"金额：{request.amount} USDC\n"
                    f"用途：{request.description}\n"
                    f"收款地址：{request.recipient}\n\n"
                    f"请在 {self.timeout_seconds // 60} 分钟内作出选择。"
                ),
                reply_markup=keyboard,
            )
        except Exception:
            self.sessions.expire_approval(
                self.chat_id,
                self.user_id,
                request.id,
            )
            raise
        self.sessions.set_approval_message(
            self.chat_id,
            self.user_id,
            request.id,
            message.message_id,
        )

        try:
            return await asyncio.wait_for(
                pending.future,
                timeout=self.timeout_seconds,
            )
        except TimeoutError:
            self.sessions.expire_approval(
                self.chat_id,
                self.user_id,
                request.id,
            )
            try:
                await self.bot.edit_message_text(
                    chat_id=self.chat_id,
                    message_id=message.message_id,
                    text="支付审批已超时，本次支付已拒绝。",
                )
            except TelegramError:
                pass
            return False
