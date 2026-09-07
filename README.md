# Slack 멘션 답변 후보 Agent

다른 사람이 Slack에서 지정 사용자를 멘션하면, 해당 메시지와 스레드 및 사용자의 과거 표현을 읽어 검토된 답변 후보 3개를 자동 생성합니다. 후보는 지정 사용자에게만 보이며, 사용자가 버튼을 눌러야 스레드에 전송됩니다.

**mention_bot.py**는 LangGraph의 '읽기 → 멘션 대상 확정 → 맥락 수집 → 초안 → 사실 검토 → 사용자 선택' 흐름을 실제 Slack Socket Mode에 연결합니다. LLM은 API 키 대신 로컬 Claude CLI(claude -p)를 사용합니다.

기존 **bot.py**는 @봇을 직접 멘션하는 단순 모드이고, **reply_agent.py**는 MCP 연결을 시험하는 CLI 모드입니다.

## Slack 앱 만들기

[slack-app-manifest.yml](slack-app-manifest.yml)을 Slack 앱 생성 화면의 **From an app manifest**에 붙여 넣으면 이벤트와 Bot Token Scope를 한 번에 설정할 수 있습니다.

직접 설정할 경우 다음 항목이 필요합니다.

1. Socket Mode를 켭니다.
2. Basic Information에서 connections:write 권한의 App-Level Token을 만들고 xapp- 토큰을 보관합니다.
3. Bot Token Scopes에 chat:write와 사용할 대화 유형의 history 권한을 넣습니다.
   - 공개 채널: channels:history
   - 비공개 채널: groups:history
   - 1:1 DM: im:history
   - 그룹 DM: mpim:history
4. Event Subscriptions에서 같은 대화 유형의 message.channels, message.groups, message.im, message.mpim 이벤트를 구독합니다.
5. Interactivity를 켜고 앱을 워크스페이스에 설치합니다.
6. 앱을 감지할 채널에 초대합니다. 비공개 채널에서는 앱과 대상 사용자 모두 채널 멤버여야 합니다.

Socket Mode는 App-Level Token의 connections:write로 WebSocket을 열며, message.channels에는 channels:history, 비공개 채널 메시지에는 groups:history가 필요합니다. 후보 표시와 전송에는 chat:write가 필요합니다.

## 설치 및 실행

~~~bash
cd /workspace/slack-reply-bot
source .venv/bin/activate
pip install -r requirements-mcp.txt

cp .env.example .env
# .env를 로컬 편집기로 열어 세 값을 입력합니다.
python mention_bot.py
~~~

또는 셸에서 SLACK_BOT_TOKEN, SLACK_APP_TOKEN, SLACK_TARGET_USER_ID를 직접 export해도 됩니다. SLACK_TARGET_USER_ID에는 답변 후보를 받을 본인의 Slack Member ID를 넣습니다. 프로필의 **More → Copy member ID**에서 확인할 수 있습니다. 토큰을 채팅이나 저장소에 남기지 마세요. .env는 Git에서 제외되어 있습니다.

## 확인 절차

1. 다른 계정이 봇을 초대한 채널에서 대상 사용자를 멘션해 질문합니다.
2. 대상 사용자에게만 후보 3개와 **이 답변 보내기** 버튼이 나타나는지 확인합니다.
3. 버튼을 누르면 선택한 문구 하나만 원래 메시지의 스레드에 전송되는지 확인합니다.
4. 후보가 나온 뒤 스레드에 새 메시지를 추가하고 예전 버튼을 누릅니다. 대화가 바뀌었다는 안내와 함께 전송이 차단되어야 합니다.

~~~bash
.venv/bin/python -m unittest discover -s tests -v
~~~

2026-09-07 기준 멘션 감지, 스레드 트리거 보존, 근거 ID 검사, 검토 실패 잠금, 맥락 변경 감지, 중복 전송 방지를 포함한 자동 테스트 16개가 통과했습니다.

## 동작 범위

- 멘션이 들어오면 후보 생성은 자동으로 시작됩니다.
- 초안과 검토가 모두 성공했을 때만 후보 3개가 표시됩니다.
- 현재 스레드는 내용의 근거로, 과거 본인 메시지는 문체 참고로 구분합니다.
- 근거 없는 완료 표현이나 호칭을 검토하고, 검토 실패 시 발송을 잠급니다.
- 전송 직전에 스레드를 다시 읽어 바뀌었으면 후보를 폐기합니다.
- Slack에는 봇 이름으로 전송됩니다.
- 후보는 프로세스 메모리에만 보관되며 재시작하면 만료됩니다.
- Slack의 ephemeral 메시지는 새로고침이나 세션 종료 뒤 사라질 수 있습니다.

## 현재 실연결 상태

코드와 로컬 자동 테스트는 완료됐습니다. 이 환경에는 SLACK_BOT_TOKEN, SLACK_APP_TOKEN, SLACK_TARGET_USER_ID가 아직 없어 실제 워크스페이스 연결은 실행하지 않았습니다. 세 값을 로컬 환경변수로 설정하면 python mention_bot.py로 바로 연결할 수 있습니다.
