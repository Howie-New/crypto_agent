#!/usr/bin/env python3
"""Telegram private-chat entry point for the x402 agent demo."""

import logging
import os
import sys
from pathlib import Path

from telegram import Update
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT / "agent-client"))

from agent import (  # noqa: E402
    AGENT_WALLET,
    LLM_PROVIDER,
    MAX_AUTO_APPROVE_AMOUNT,
    X402Agent,
)
from telegram_channel.sessions import TelegramSessionManager  # noqa: E402
from telegram_channel.ui import (  # noqa: E402
    TelegramApprovalHandler,
    TelegramEventSink,
    send_long_message,
)


LOGGER = logging.getLogger(__name__)
PAYMENT_CALLBACK_PATTERN = r"^pay:[0-9a-f]{32}:(approve|reject)$"


def parse_allowed_user_ids(raw_value: str) -> set[int]:
    allowed: set[int] = set()
    for value in raw_value.split(","):
        value = value.strip()
        if not value:
            continue
        try:
            allowed.add(int(value))
        except ValueError as exc:
            raise ValueError(
                "TELEGRAM_ALLOWED_USER_IDS must contain comma-separated numeric IDs"
            ) from exc
    return allowed


def is_authorized(update: Update, allowed_user_ids: set[int]) -> bool:
    user = update.effective_user
    chat = update.effective_chat
    return bool(
        user
        and chat
        and chat.type == "private"
        and user.id in allowed_user_ids
    )


def get_sessions(application: Application) -> TelegramSessionManager:
    return application.bot_data["sessions"]


def get_allowed_user_ids(application: Application) -> set[int]:
    return application.bot_data["allowed_user_ids"]


async def reject_unauthorized(update: Update) -> None:
    if update.callback_query:
        await update.callback_query.answer("未授权访问", show_alert=True)
    elif update.effective_message:
        await update.effective_message.reply_text("该 Bot 仅向已授权的私聊用户开放。")


async def start_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if not is_authorized(update, get_allowed_user_ids(context.application)):
        await reject_unauthorized(update)
        return
    await update.effective_message.reply_text(
        "x402 Agent Telegram Demo 已就绪。\n\n"
        "直接发送任务即可开始。\n"
        "/new - 清空当前会话\n"
        "/status - 查看运行状态"
    )


async def new_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if not is_authorized(update, get_allowed_user_ids(context.application)):
        await reject_unauthorized(update)
        return

    user = update.effective_user
    chat = update.effective_chat
    session = get_sessions(context.application).get(chat.id, user.id)
    if session.busy:
        await update.effective_message.reply_text(
            "当前任务仍在执行，请先完成支付审批或等待任务结束。"
        )
        return

    get_sessions(context.application).reset(chat.id, user.id)
    await update.effective_message.reply_text("当前会话和钱包账本已重置。")


async def status_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if not is_authorized(update, get_allowed_user_ids(context.application)):
        await reject_unauthorized(update)
        return

    user = update.effective_user
    chat = update.effective_chat
    session = get_sessions(context.application).get(chat.id, user.id)
    model = (
        os.getenv("ANTHROPIC_MODEL")
        if LLM_PROVIDER in ("anthropic", "claude")
        else os.getenv("OPENAI_MODEL")
    )
    await update.effective_message.reply_text(
        "运行状态\n\n"
        f"模型提供方：{LLM_PROVIDER}\n"
        f"模型：{model or '自动检测'}\n"
        f"钱包：{AGENT_WALLET}\n"
        f"自动支付阈值：{MAX_AUTO_APPROVE_AMOUNT} USDC\n"
        f"会话消息数：{len(session.conversation_history)}\n"
        f"任务状态：{'执行中' if session.busy else '空闲'}"
    )


async def run_agent_task(
    application: Application,
    chat_id: int,
    user_id: int,
    text: str,
) -> None:
    sessions = get_sessions(application)
    session = sessions.get(chat_id, user_id)
    agent: X402Agent | None = None
    try:
        sink = TelegramEventSink(application.bot, chat_id)
        approval_handler = TelegramApprovalHandler(
            bot=application.bot,
            sessions=sessions,
            chat_id=chat_id,
            user_id=user_id,
            timeout_seconds=application.bot_data["approval_timeout_seconds"],
        )
        agent = X402Agent(
            event_handler=sink,
            approval_handler=approval_handler,
            wallet_state=session.wallet_state,
        )
        agent.conversation_history = list(session.conversation_history)
        await agent.connect_mcp_server()
        result = await agent.chat(text)
        session.conversation_history = list(agent.conversation_history)
        await send_long_message(
            application.bot,
            chat_id,
            result or "任务已完成，但模型没有返回最终文本。",
        )
    except Exception:
        LOGGER.exception("Telegram agent task failed for user %s", user_id)
        await application.bot.send_message(
            chat_id=chat_id,
            text="任务执行失败，请检查服务状态和日志后重试。",
        )
    finally:
        pending = session.pending_approval
        if pending is not None:
            sessions.expire_approval(
                chat_id,
                user_id,
                pending.request.id,
            )
        if agent is not None:
            try:
                await agent.close()
            except Exception:
                LOGGER.exception("Failed to close MCP session")
        session.busy = False
        session.active_task = None


async def message_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if not is_authorized(update, get_allowed_user_ids(context.application)):
        await reject_unauthorized(update)
        return

    user = update.effective_user
    chat = update.effective_chat
    text = update.effective_message.text.strip()
    session = get_sessions(context.application).get(chat.id, user.id)
    if session.busy:
        await update.effective_message.reply_text(
            "上一项任务仍在执行，请先完成支付审批或等待任务结束。"
        )
        return

    session.busy = True
    await update.effective_message.reply_text("已收到任务，正在处理。")
    session.active_task = context.application.create_task(
        run_agent_task(
            context.application,
            chat.id,
            user.id,
            text,
        ),
        update=update,
    )


async def payment_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if not is_authorized(update, get_allowed_user_ids(context.application)):
        await reject_unauthorized(update)
        return

    query = update.callback_query
    _, request_id, decision = query.data.split(":", 2)
    approved = decision == "approve"
    user = update.effective_user
    chat = update.effective_chat
    pending = get_sessions(context.application).resolve_approval(
        chat.id,
        user.id,
        request_id,
        approved,
    )
    if pending is None:
        await query.answer("该审批请求已失效或已处理。", show_alert=True)
        return

    await query.answer("已批准" if approved else "已拒绝")
    await query.edit_message_text(
        "支付已获批准，Agent 将继续执行。"
        if approved
        else "支付已被拒绝，本次操作不会执行。"
    )


async def error_handler(
    update: object,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    LOGGER.error("Telegram update failed", exc_info=context.error)


def build_application() -> Application:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token or token == "your_telegram_bot_token_here":
        raise RuntimeError("TELEGRAM_BOT_TOKEN is required")

    allowed_user_ids = parse_allowed_user_ids(
        os.getenv("TELEGRAM_ALLOWED_USER_IDS", "")
    )
    if not allowed_user_ids:
        raise RuntimeError("TELEGRAM_ALLOWED_USER_IDS must contain at least one user ID")

    approval_timeout_seconds = int(
        os.getenv("TELEGRAM_APPROVAL_TIMEOUT_SECONDS", "300")
    )
    if approval_timeout_seconds <= 0:
        raise RuntimeError("TELEGRAM_APPROVAL_TIMEOUT_SECONDS must be positive")

    application = ApplicationBuilder().token(token).build()
    application.bot_data["sessions"] = TelegramSessionManager()
    application.bot_data["allowed_user_ids"] = allowed_user_ids
    application.bot_data["approval_timeout_seconds"] = approval_timeout_seconds

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("new", new_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(
        CallbackQueryHandler(
            payment_callback,
            pattern=PAYMENT_CALLBACK_PATTERN,
        )
    )
    application.add_handler(
        MessageHandler(
            filters.ChatType.PRIVATE & filters.TEXT & ~filters.COMMAND,
            message_handler,
        )
    )
    application.add_error_handler(error_handler)
    return application


def main() -> None:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    application = build_application()
    LOGGER.info("Starting Telegram bot with long polling")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
