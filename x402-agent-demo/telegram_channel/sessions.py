import asyncio
from dataclasses import dataclass, field

from agent import PaymentApprovalRequest, WalletState


SessionKey = tuple[int, int]


@dataclass
class PendingApproval:
    request: PaymentApprovalRequest
    future: asyncio.Future[bool]
    message_id: int | None = None


@dataclass
class TelegramSession:
    conversation_history: list[dict] = field(default_factory=list)
    wallet_state: WalletState = field(default_factory=WalletState)
    busy: bool = False
    active_task: asyncio.Task | None = None
    pending_approval: PendingApproval | None = None


class TelegramSessionManager:
    """In-memory session and approval state keyed by chat and user."""

    def __init__(self):
        self._sessions: dict[SessionKey, TelegramSession] = {}

    def get(self, chat_id: int, user_id: int) -> TelegramSession:
        return self._sessions.setdefault((chat_id, user_id), TelegramSession())

    def clear_history(self, chat_id: int, user_id: int) -> None:
        self.get(chat_id, user_id).conversation_history.clear()

    def reset(self, chat_id: int, user_id: int) -> TelegramSession:
        session = TelegramSession()
        self._sessions[(chat_id, user_id)] = session
        return session

    def begin_approval(
        self,
        chat_id: int,
        user_id: int,
        request: PaymentApprovalRequest,
    ) -> PendingApproval:
        session = self.get(chat_id, user_id)
        if session.pending_approval is not None:
            raise RuntimeError("A payment approval is already pending")

        pending = PendingApproval(
            request=request,
            future=asyncio.get_running_loop().create_future(),
        )
        session.pending_approval = pending
        return pending

    def set_approval_message(
        self,
        chat_id: int,
        user_id: int,
        request_id: str,
        message_id: int,
    ) -> None:
        pending = self.get(chat_id, user_id).pending_approval
        if pending and pending.request.id == request_id:
            pending.message_id = message_id

    def resolve_approval(
        self,
        chat_id: int,
        user_id: int,
        request_id: str,
        approved: bool,
    ) -> PendingApproval | None:
        session = self.get(chat_id, user_id)
        pending = session.pending_approval
        if pending is None or pending.request.id != request_id:
            return None

        session.pending_approval = None
        if not pending.future.done():
            pending.future.set_result(approved)
        return pending

    def expire_approval(
        self,
        chat_id: int,
        user_id: int,
        request_id: str,
    ) -> PendingApproval | None:
        session = self.get(chat_id, user_id)
        pending = session.pending_approval
        if pending is None or pending.request.id != request_id:
            return None

        session.pending_approval = None
        if not pending.future.done():
            pending.future.cancel()
        return pending
