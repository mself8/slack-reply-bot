"""Slack에서 지정 사용자가 멘션되면 검토된 답변 후보를 자동 생성한다.

Socket Mode의 message 이벤트를 받아 LangGraph 후보 생성 파이프라인을 실행한다.
후보는 멘션된 사용자에게만 보이며, 사용자가 버튼을 눌러야 전송된다.
"""
from __future__ import annotations

import asyncio
from collections import OrderedDict
import logging
import os
import re
import uuid

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from dotenv import load_dotenv

from reply_agent import ClaudeModel, approve_and_send, build_app


logger = logging.getLogger(__name__)


def is_target_mention(event: dict, target_user: str) -> bool:
    if event.get("subtype") or event.get("bot_id") or event.get("user") == target_user:
        return False
    text = event.get("text", "")
    return isinstance(text, str) and re.search(
        rf"<@{re.escape(target_user)}(?:\|[^>]+)?>", text
    ) is not None


def normalize_messages(rows: list[dict]) -> list[dict]:
    messages = []
    for row in rows:
        if row.get("subtype") or row.get("bot_id"):
            continue
        message = {key: row.get(key, "") for key in ("user", "text", "ts", "thread_ts")}
        if all(
            isinstance(message[key], str) and message[key]
            for key in ("user", "text", "ts")
        ):
            messages.append(message)
    return sorted(messages, key=lambda message: float(message["ts"]))


class DirectSlackGateway:
    """Slack WebClient를 기존 Agent의 gateway 인터페이스에 맞춘다."""

    def __init__(self, client, history_limit: int = 200, trigger_event: dict | None = None):
        self.client = client
        self.history_limit = history_limit
        normalized = normalize_messages([trigger_event]) if trigger_event else []
        self.trigger_event = normalized[0] if normalized else None

    async def recent(self, channel):
        response = await asyncio.to_thread(
            self.client.conversations_history,
            channel=channel,
            limit=min(self.history_limit, 100),
        )
        messages = normalize_messages(list(reversed(response["messages"])))
        if self.trigger_event and not any(
            message["ts"] == self.trigger_event["ts"] for message in messages
        ):
            messages.append(self.trigger_event)
            messages.sort(key=lambda message: float(message["ts"]))
        return messages

    async def history(self, channel, user):
        response = await asyncio.to_thread(
            self.client.conversations_history,
            channel=channel,
            limit=min(self.history_limit, 100),
        )
        return [
            message
            for message in normalize_messages(list(reversed(response["messages"])))
            if message["user"] == user
        ]

    async def thread(self, channel, ts):
        response = await asyncio.to_thread(
            self.client.conversations_replies, channel=channel, ts=ts, limit=100
        )
        return normalize_messages(response["messages"])

    async def send(self, channel, ts, text):
        return await asyncio.to_thread(
            self.client.chat_postMessage, channel=channel, thread_ts=ts, text=text
        )


def create_app(bot_token: str, target_user: str):
    app = App(token=bot_token)
    pending: "OrderedDict[str, tuple[dict, int]]" = OrderedDict()
    processed: "OrderedDict[str, None]" = OrderedDict()

    def mark_once(event_id: str) -> bool:
        if event_id in processed:
            return False
        processed[event_id] = None
        while len(processed) > 500:
            processed.popitem(last=False)
        return True

    @app.event("message")
    def on_message(event, client):
        if not is_target_mention(event, target_user) or not mark_once(event["ts"]):
            return
        channel = event["channel"]
        gateway = DirectSlackGateway(client, trigger_event=event)
        try:
            state = asyncio.run(
                build_app(gateway, ClaudeModel()).ainvoke(
                    {
                        "channel": channel,
                        "user": target_user,
                        "target_ts": event["ts"],
                    }
                )
            )
            if state.get("decision") != "reply":
                reason = state.get("reason") or state.get("review_reason", "")
                client.chat_postEphemeral(
                    channel=channel,
                    user=target_user,
                    text=f"답변 후보를 만들지 않았습니다: {reason}",
                )
                return
            blocks = []
            for index, candidate in enumerate(state["candidates"]):
                key = uuid.uuid4().hex
                pending[key] = (state, index)
                blocks.append(
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"*후보 {index + 1}*\n{candidate['text']}",
                        },
                        "accessory": {
                            "type": "button",
                            "text": {
                                "type": "plain_text",
                                "text": "이 답변 보내기",
                            },
                            "action_id": "send_reviewed_candidate",
                            "value": key,
                        },
                    }
                )
            while len(pending) > 300:
                pending.popitem(last=False)
            client.chat_postEphemeral(
                channel=channel,
                user=target_user,
                text="검토된 답변 후보 3개가 준비됐습니다.",
                blocks=blocks,
            )
        except Exception:
            logger.exception("Slack 멘션의 답변 후보 생성 실패")
            client.chat_postEphemeral(
                channel=channel,
                user=target_user,
                text=(
                    "답변 후보 생성에 실패했습니다. "
                    "로그에서 Slack 권한과 Claude CLI 상태를 확인해 주세요."
                ),
            )

    @app.action("send_reviewed_candidate")
    def on_send(ack, body, client, respond):
        ack()
        key = body["actions"][0]["value"]
        item = pending.pop(key, None)
        if item is None:
            respond(
                text="후보가 만료됐습니다. 최신 멘션에서 다시 생성해 주세요.",
                replace_original=True,
            )
            return
        state, index = item
        gateway = DirectSlackGateway(client)
        try:
            asyncio.run(
                approve_and_send(
                    gateway,
                    state,
                    index,
                    state["candidates"][index]["text"],
                )
            )
            respond(text="선택한 답변을 스레드에 보냈습니다.", replace_original=True)
        except ValueError as error:
            respond(text=str(error), replace_original=True)

    return app


def main():
    load_dotenv()
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
    bot_token = os.environ["SLACK_BOT_TOKEN"]
    app_token = os.environ["SLACK_APP_TOKEN"]
    target_user = os.environ["SLACK_TARGET_USER_ID"]
    SocketModeHandler(create_app(bot_token, target_user), app_token).start()


if __name__ == "__main__":
    main()
