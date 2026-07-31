# 슬랙 답변 후보 봇

채널에서 **@봇 멘션** → 나에게만 보이는 답변 후보 3개 + 버튼 → 클릭하면 스레드에 발송.
LLM은 API 키 대신 **Claude Code CLI(`claude -p`, 구독)** 를 사용한다. Socket Mode라 공인 IP가 필요 없다.

## 1. Slack 앱 설정 (5~10분)

[api.slack.com/apps](https://api.slack.com/apps) → **Create New App → From scratch** → 이름 예: `답변봇`, 워크스페이스 선택.

1. **Socket Mode** (왼쪽 메뉴) → 토글 On → App-Level Token 생성, scope는 `connections:write` → **`xapp-`로 시작하는 토큰 복사**
2. **Event Subscriptions** → Enable → Subscribe to bot events에 **`app_mention`** 추가 → Save
3. **OAuth & Permissions** → Bot Token Scopes에 추가:
   - `app_mentions:read`, `chat:write`, `channels:history`, `groups:history`, `im:history`
   → 상단 **Install to Workspace** → **`xoxb-`로 시작하는 토큰 복사**
   - ⚠️ 연구실 워크스페이스는 관리자 승인이 필요할 수 있음 (승인 요청 화면이 뜨면 요청)
4. 봇을 쓸 채널에서 `/invite @답변봇`

## 2. 연구실 서버 설치

```bash
# 코드 복사 후 해당 디렉터리에서
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Claude Code CLI 설치 + 로그인 (구독 계정)
curl -fsSL https://claude.ai/install.sh | bash
claude   # 첫 실행에서 로그인 진행 후 종료

# 토큰 설정
export SLACK_BOT_TOKEN=xoxb-...
export SLACK_APP_TOKEN=xapp-...

# 실행
python bot.py    # "⚡️ Bolt app is running!" 이 뜨면 성공
```

### 상시 구동 (tmux)

```bash
tmux new -s replybot
# (tmux 안에서) source .venv/bin/activate && export 토큰 2개 && python bot.py
# Ctrl+B, D 로 빠져나오면 백그라운드에서 계속 돎
```

서버 재부팅 시엔 재시작 필요 — 영구화하려면 systemd 서비스로 등록(`ExecStart=... python bot.py`, 환경변수는 `EnvironmentFile=`에).

## 3. 테스트 절차

1. `python bot.py` 실행 상태에서, 봇을 초대한 채널에 아무 대화를 몇 줄 남긴다
2. `@답변봇` 멘션 → 몇 초~수십 초 내에 **나에게만 보이는** 후보 3개가 뜨는지 확인
3. 버튼 클릭 → 스레드에 후보가 발송되고 안내가 "✅ 발송됨"으로 바뀌는지 확인
4. 안 되면: 터미널 로그 확인 → 토큰 오타 / 채널 미초대 / `claude` 로그인 안 됨이 3대 원인

## 한계와 다음 단계

- **봇 이름으로 발송됨.** "송윤 이름으로" 발송하려면 User Token(`xoxp-`, scope `chat:write`)을 추가 발급받아 `chat_postMessage`를 user token으로 호출하도록 수정 (v2).
- 후보는 프로세스 메모리에만 보관 — 봇 재시작 시 이전 버튼은 만료 처리됨.
- DM에서 쓰려면 봇과의 DM에서 멘션 없이 동작하게 `message.im` 이벤트 추가 (v2).
