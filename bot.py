"""슬랙 멘션 답변 후보 봇.

@봇 멘션 → 스레드 맥락 수집 → Claude Code CLI(claude -p, 구독)로 후보 3개 생성
→ 멘션한 사람에게만 보이는 메시지로 제시 → 버튼 클릭 시 스레드에 발송.
Socket Mode라 공인 IP·포트 개방 불필요.
"""
import os
import subprocess
import uuid
from collections import OrderedDict

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

BOT_TOKEN = os.environ["SLACK_BOT_TOKEN"]    # xoxb-
APP_TOKEN = os.environ["SLACK_APP_TOKEN"]    # xapp-
CLAUDE_BIN = os.environ.get("CLAUDE_BIN", "claude")

app = App(token=BOT_TOKEN)

# 후보 보관소: uuid -> {"text", "channel", "thread_ts"}  (최근 300개만 유지)
candidates: "OrderedDict[str, dict]" = OrderedDict()


def remember(entry: dict) -> str:
    key = uuid.uuid4().hex
    candidates[key] = entry
    while len(candidates) > 300:
        candidates.popitem(last=False)
    return key


def collect_context(client, channel: str, event: dict) -> str:
    """멘션이 달린 스레드(없으면 채널 최근) 대화를 시간순 텍스트로."""
    thread_ts = event.get("thread_ts")
    if thread_ts:
        resp = client.conversations_replies(channel=channel, ts=thread_ts, limit=15)
        messages = resp["messages"]
    else:
        resp = client.conversations_history(channel=channel, limit=10)
        messages = list(reversed(resp["messages"]))
    lines = []
    for m in messages:
        if m.get("subtype"):  # 시스템 메시지 제외
            continue
        lines.append(f"<{m.get('user', '?')}>: {m.get('text', '')}")
    return "\n".join(lines)


def generate_candidates(context: str) -> list[str]:
    prompt = (
        "아래 슬랙 대화에서 '송윤'이 멘션됐다. 송윤 입장에서 보낼 답변 후보 3개를 작성하라. "
        "각 후보는 3문장 이내, 한국어, 대화 톤에 맞게. "
        "후보 사이는 '---' 한 줄로 구분하고, 후보 텍스트만 출력하라.\n\n"
        f"[대화]\n{context}"
    )
    result = subprocess.run(
        [CLAUDE_BIN, "-p", prompt], capture_output=True, text=True, timeout=120
    )
    if result.returncode != 0:
        raise RuntimeError(f"claude CLI 실패: {result.stderr.strip()[:300]}")
    parts = [p.strip() for p in result.stdout.split("---") if p.strip()]
    if not parts:
        raise RuntimeError("claude CLI가 빈 응답을 반환")
    return parts[:3]


@app.event("app_mention")
def on_mention(event, client):
    channel = event["channel"]
    user = event["user"]
    # 답변이 달릴 위치: 멘션이 스레드에 있으면 그 스레드, 아니면 멘션 메시지의 스레드
    reply_ts = event.get("thread_ts") or event["ts"]
    try:
        context = collect_context(client, channel, event)
        cands = generate_candidates(context)
    except Exception as e:
        client.chat_postEphemeral(
            channel=channel, user=user, text=f"⚠️ 후보 생성 실패: {e}"
        )
        return

    blocks = []
    buttons = []
    for i, text in enumerate(cands, start=1):
        key = remember({"text": text, "channel": channel, "thread_ts": reply_ts})
        blocks.append(
            {"type": "section", "text": {"type": "mrkdwn", "text": f"*후보 {i}*\n{text}"}}
        )
        buttons.append(
            {
                "type": "button",
                "text": {"type": "plain_text", "text": f"{i} 발송"},
                "action_id": f"send_candidate_{i}",
                "value": key,
            }
        )
    blocks.append({"type": "actions", "elements": buttons})
    client.chat_postEphemeral(
        channel=channel,
        user=user,
        text="답변 후보가 준비됐습니다.",
        blocks=blocks,
    )


@app.action("send_candidate_1")
@app.action("send_candidate_2")
@app.action("send_candidate_3")
def on_send(ack, body, client, respond):
    ack()
    key = body["actions"][0]["value"]
    entry = candidates.pop(key, None)
    if entry is None:
        respond(text="⚠️ 후보가 만료됐습니다. 다시 멘션해 주세요.", replace_original=True)
        return
    client.chat_postMessage(
        channel=entry["channel"], thread_ts=entry["thread_ts"], text=entry["text"]
    )
    respond(text="✅ 발송됨", replace_original=True)


if __name__ == "__main__":
    SocketModeHandler(app, APP_TOKEN).start()
