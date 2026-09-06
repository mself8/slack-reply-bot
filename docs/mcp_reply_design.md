# Slack MCP 기반 개인 문체 답변 추천 — 2026-09-06

## 사용자 요구
Slack 대화 내역을 MCP로 읽고 답변이 필요한 상황을 판단한다. 본인의 과거 답변에서 표현 방식과 말투를 참고해 후보를 추천하고, 사용자가 고른 답변만 전송한다.

## 구현
`reply_agent.py`의 LangGraph:

1. **read_recent**: 사용자가 지정한 채널의 최근 메시지를 MCP로 조회한다.
2. **triage**: LLM이 답변할 대상을 하나 고르거나 `no_action`으로 종료한다. 본인 발언이나 조회되지 않은 메시지는 대상으로 허용하지 않는다.
3. **context**: 해당 스레드를 읽고 같은 채널에서 본인 과거 메시지를 MCP 검색한다. 다른 사람·봇·현재 스레드·미래 메시지를 제외한다. 현재 맥락과 겹치는 문자 2-gram 비율로 최대 6개를 고른다.
4. **draft**: 전체 스레드를 보고 필요 여부를 다시 판단한다. 과거 발언은 문체 참고로만 제공한다. 현재 사실의 근거와 문체 참고 메시지 ID를 나눠 받은 뒤 존재 여부를 코드로 검사한다.
5. **review**: 후보 문구를 현재 스레드와 다시 대조해 과거 문체에만 있는 진행 상태·완료 표현을 수정한다. LLM 검토이므로 사실성 보장은 아니며 사용자가 최종 확인한다.
검토 응답이 잘못되거나 시간이 초과되면 `needs_review`로 종료해 발송할 수 없게 한다.

6. **선택**: 기본 실행은 추천만 한다. `--interactive`에서는 사용자가 출력된 후보 번호를 선택해야 전송한다. 전송 직전 스레드를 다시 읽어 변경되면 재추천을 요구한다. 전송 결과가 불명확한 경우 자동 재발송하지 않는다.

별도 학습이나 파인튜닝이 아니라 **본인 메시지 검색 + 예제 기반 생성**이다. 참고 예제와 표현 요약을 출력해 검토 가능하게 했다. 도구 호출은 코드에 정해진 MCP 작업에 한정되며, 대화 내용을 근거로 임의 도구를 실행하지 않는다.

## 실행
```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-mcp.txt
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python demo_mcp.py
.venv/bin/python demo_mcp.py --live-model
```

`docs/mcp_demo.html`은 고정 모델 + 예제 MCP 서버 데모. `--live-model`은 같은 예제 서버에서 실제 Claude로 판단·생성한다. **실제 Slack 계정 조회와 구분한다.** 로컬 테스트 서버도 MCP 초기화·도구 목록·도구 호출을 실제 사용한다.

## 실제 Slack MCP 연결
서버마다 도구 이름·인자·응답 모양이 다르므로 임의로 Slack API 이름을 가정하지 않는다. `mcp_gateway.py`가 stdio 또는 Streamable HTTP 서버에 연결해 도구 목록과 JSON 스키마를 확인하고, 사용자가 정한 `bindings`로 recent/history/thread/send를 연결한다. `bot.py`의 기존 Slack Bolt 경로와 독립되어 있다.

1. 먼저 현재 쓰는 MCP의 접속 설정과 인증이 필요하다. Claude 웹에 연결한 OAuth가 이 Python 앱으로 자동 전달되는 것은 아니다.
2. `--list-tools`로 실제 서버 스키마를 확인한다.
3. `bindings`의 도구명·인자·결과 경로를 실제 스키마에 맞춘다. `$channel`, `$user`, `$query`, `$ts`, `$text`는 런타임 값이다.
4. `--channel`과 `--user`는 실제 채널 ID·본인 사용자 ID를 지정한다.

```bash
.venv/bin/python reply_agent.py --config /path/to/private-mcp.json --list-tools
.venv/bin/python reply_agent.py --config /path/to/private-mcp.json --channel C123ABC --user U123ABC
# 후보를 직접 확인하고 발송할 때만:
.venv/bin/python reply_agent.py --config /path/to/private-mcp.json --channel C123ABC --user U123ABC --interactive
```

`examples/mcp-config.template.json`은 연결 형식 템플릿이며 그대로는 실제 서버에 연결되지 않는다. 헤더의 값은 환경변수 이름으로 참조한다. OAuth 로그인·갱신 UI는 구현하지 않았으므로 인증된 MCP 서버 또는 기존 인증 경로를 확인해야 한다. 이 환경에서는 Slack MCP 연결이 확인되지 않아 실제 계정 조회·발송은 미검증이다.

## 제품 판단과 한계
- 전체 회사 대화를 무제한 수집하지 않고 사용자가 지정한 채널·서버 응답 범위 안에서 동작한다. 메시지 페이지네이션은 현재 미구현이며 조회 범위 내 추천이다.
- 원문 사실을 보증하는 검증기가 아니라 메시지 출처 ID의 존재를 검사한다. 문체 적합성·약속 날조·관련성은 실제 사용자 평가가 필요하다.
- 문체 표본이 5개 미만이면 제한된 근거로 표시한다. 채널 밖 문체는 섞지 않는다.
- 단발 실행 프로토타입이며 상시 감시·스케줄링은 미구현이다.
- 생성된 추천은 프로세스 메모리에 보관한다. 발송 중복 방지는 해당 실행 안에서만 유효하다.
- 전송 직전 재조회와 실제 전송 사이에 새 메시지가 올 수 있다. 원자적 Slack 트랜잭션을 보장하지 않는다.
- 예제 인물/대화로 테스트했다. 실제 사용자 문체 정확도 수치나 운영 성과로 주장하지 않는다.

## 면접 설명
“말투를 비슷하게 만들기 위해 과거 답변을 참고하되, 과거 일정이나 약속이 현재 사실처럼 섞이면 안 된다고 봤습니다. 현재 스레드와 문체 예시를 구분해 제공하고, 답변이 필요 없는 경우는 건너뛰게 했습니다. 추천 후 대화가 바뀌면 재추천하고 최종 발송은 사용자 선택으로 남겼습니다.”

이번 추가는 AI 코딩 도구를 활용한 구현이다. 사용자가 요구·방향을 제시했고, 구현과 테스트를 보조받았다. 실제 계정 연결·사용자 평가가 끝나기 전에는 해당 성과를 주장하지 않는다.

참고: https://docs.slack.dev/ai/slack-mcp-server/ 및 https://github.com/modelcontextprotocol/python-sdk/tree/v1.x

## 확인한 결과
- 자동 테스트 11개 통과: 본인 과거 발언 필터링, 출처 검사, 미선택 발송 차단, 대화 변경 차단, 검토 실패 시 발송 차단 등을 확인했다. 모델 정확도 측정은 아니다.
- 로컬 MCP 서버 + 실제 Claude 실행에서 조회·판단·문체 참고·후보 검토까지 완료했다. 검토 단계가 근거 없는 “확인했습니다”와 현재 대화에서 확인되지 않은 “교수님” 호칭을 제거했다. 단일 예제 결과이며 일반적인 개선율은 측정하지 않았다.

## 실제 Slack 연결 절차 (2026-09-06 추가)

현재 상태: `reply_agent.py`는 Slack API를 직접 호출하지 않는다. MCP 서버 하나에 붙어 `recent/history/thread/send` 네 작업을 그 서버의 도구로 보낸다. 지금까지 붙여 본 서버는 `tests/fixture_mcp.py`(가짜)뿐이다. **실제 Slack 계정에서 돌린 적은 없다.**

Slack MCP 서버 후보 두 개(README 확인, 2026-09-06):

| 서버 | 도구 | 인증 | 비고 |
|---|---|---|---|
| `korotovsky/slack-mcp-server` (Go) | `conversations_history(channel_id, limit)`, `conversations_replies(channel_id, thread_ts)`, `conversations_search_messages(filter_users_from, filter_in_channel, …)`, `conversations_add_message(channel_id, payload, thread_ts)` | xoxp 또는 xoxb, 또는 xoxc+xoxd | 네 작업이 전부 있다. **전송 도구는 기본 꺼짐** → `SLACK_MCP_ADD_MESSAGE_TOOL`에 테스트 채널 ID만 넣어 켠다. 응답 JSON. 템플릿 `examples/mcp-config.slack-korotovsky.template.json` |
| `@modelcontextprotocol/server-slack` (참조 구현, 보관됨) | `slack_get_channel_history(channel_id, limit)`, `slack_get_thread_replies(channel_id, thread_ts)`, `slack_reply_to_thread(channel_id, thread_ts, text)` | xoxb + `SLACK_TEAM_ID`, 스코프 channels:history·channels:read·chat:write·users:read | **검색 도구가 없다** → `history`를 `slack_get_channel_history`에 묶고 본인 메시지 필터는 코드(`own_examples`)에 맡긴다. `npx -y @modelcontextprotocol/server-slack` |

순서:
1. Slack 접근이 되는 머신(랩 서버·노트북)에서 서버를 띄운다. 이 샌드박스는 slack.com egress가 없다.
2. `python reply_agent.py --config <설정> --list-tools`로 도구 이름·스키마를 확인한다. 바인딩의 인자 이름이 스키마와 다르면 시작 시 거부된다.
3. 원시 호출 한 번으로 응답 모양을 보고 `result_path`·`fields`(user/text/ts/thread_ts가 어느 키인지)를 채운다. `ts`는 숫자형 문자열이어야 정렬된다.
4. **먼저 `send` 바인딩을 뺀 설정으로** 추천만 돌린다(바인딩에 있는 도구가 서버에 없으면 시작이 안 되므로, 전송 도구를 끈 상태에선 `send` 항목 자체를 지운다).
5. 전송은 테스트 채널(또는 나에게 보내는 DM)에서만 `--interactive`로 켠다. 선택한 후보 하나만 나간다.
6. 결과는 `--out`으로 저장하되 개인 대화가 들어가므로 레포에 올리지 않는다.
