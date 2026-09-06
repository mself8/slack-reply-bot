"""End-to-end MCP demo with synthetic history. --live-model uses Claude for reasoning."""
import argparse
import asyncio
import html
import json
from pathlib import Path
import sys
from mcp_gateway import connect
from reply_agent import build_app,ClaudeModel

class FixtureModel:
    async def complete(self,instruction,payload):
        if instruction.startswith('TRIAGE'): return {'decision':'reply','target_ts':'20.0','reason':'사용자를 직접 멘션한 평가표 확인 요청'}
        return {'decision':'reply','style_summary':'짧은 존댓말, 확인 요청, 제한적인 느낌표 사용','candidates':[
            {'text':text,'intent':intent,'evidence_ts':['20.0'],'style_ts':['11.0','13.0']}
            for text,intent in [('어떤 모델의 비교가 빠졌는지 알려주실 수 있을까요?','누락 범위 확인'),('모델별 비교 항목을 확인하면 될까요? 추가로 필요한 기준도 말씀 부탁드립니다!','기준 확인'),('말씀하신 결과표가 어느 파일인지 확인 부탁드립니다.','대상 파일 확인')]]}

def config(root):
    return {'connection':{'transport':'stdio','command':sys.executable,'args':[str(root/'tests/fixture_mcp.py')]},'bindings':{
        'recent':{'tool':'test_recent','arguments':{'channel':'$channel'}},
        'history':{'tool':'test_search','arguments':{'query':'$query'},'result_path':'messages.matches'},
        'thread':{'tool':'test_thread','arguments':{'channel':'$channel','ts':'$ts'}},
        'send':{'tool':'test_send','arguments':{'channel':'$channel','ts':'$ts','text':'$text'}}}}

async def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--live-model',action='store_true'); args=parser.parse_args()
    root=Path(__file__).parent
    async with connect(config(root)) as gateway:
        model=ClaudeModel() if args.live_model else FixtureModel()
        result=await build_app(gateway,model).ainvoke({'channel':'CTEST','user':'UME'})
        result['mcp_calls']=gateway.calls
        assert not any(x['operation']=='send' for x in gateway.calls)
    result['test_mode']='synthetic MCP server + '+('live Claude model' if args.live_model else 'scripted model')
    label='live_model_demo' if args.live_model else 'mcp_demo'
    (root/'docs'/f'{label}.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    candidates=''.join(f'<section><h2>후보 {i}</h2><p class="reply">{html.escape(c["text"])}</p><small>{html.escape(c.get("intent",""))}</small><button onclick="navigator.clipboard.writeText(this.parentElement.querySelector(\'.reply\').textContent)">문구 복사</button></section>' for i,c in enumerate(result.get('candidates',[]),1))
    refs=''.join(f'<li>{html.escape(m["text"])}</li>' for m in result.get('profile',{}).get('examples',[]))
    document='''<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>내 말투로 답변 추천</title><style>body{font:17px/1.7 system-ui;max-width:900px;margin:48px auto;padding:0 24px;background:#f4f6fa;color:#17243b}section{background:#fff;border-radius:16px;padding:22px;margin:16px 0}button{display:block;border:0;border-radius:8px;padding:10px 16px;margin-top:12px;cursor:pointer;background:#dce9ff}small{color:#53647a}</style><h1>대화 맥락과 내 말투를 함께 봅니다</h1><p>교수님: “평가 결과표에 모델별 비교가 빠진 것 같은데 확인 가능한가요?”</p><p>'''+html.escape(result.get('reason',''))+'</p><p>판단: '+html.escape(result.get('decision',''))+'</p><p>'+html.escape(result.get('review_reason',''))+'</p>'+candidates+'<details><summary>말투 참고에 사용한 본인 발언</summary><ul>'+refs+'</ul></details><p><small>'+html.escape(result['test_mode'])+' · 예제 인물과 대화입니다. MCP 조회는 로컬 테스트 서버에서 실제 수행했고 Slack 실계정 조회·발송은 하지 않았습니다. 복사 버튼은 Slack으로 발송하지 않습니다.</small></p></html>'
    (root/'docs'/f'{label}.html').write_text(document)
    print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__': asyncio.run(main())
