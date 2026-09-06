import copy
import unittest
from reply_agent import own_examples,build_app,approve_and_send
from mcp_gateway import normalize

THREAD=[{'user':'UOTHER','ts':'20.0','text':'<@UME> 평가표 확인 부탁드립니다.','thread_ts':''}]
HISTORY=[{'user':'UME','ts':'10.0','text':'확인했습니다! 평가표 확인 부탁드립니다.','thread_ts':''},
         {'user':'UOTHER','ts':'11.0','text':'야 빨리','thread_ts':''},
         {'user':'UME','ts':'21.0','text':'미래 메시지','thread_ts':''}]
class Gateway:
    def __init__(self): self.messages=copy.deepcopy(THREAD); self.sent=[]; self.reads=[]
    async def recent(self,channel): self.reads.append('recent'); return copy.deepcopy(self.messages)
    async def thread(self,channel,ts): self.reads.append('thread'); return copy.deepcopy(self.messages)
    async def history(self,channel,user): self.reads.append('history'); return copy.deepcopy(HISTORY)
    async def send(self,channel,ts,text): self.sent.append(text); return {'ok':True}
class Model:
    def __init__(self,mode='reply'): self.mode=mode
    async def complete(self,instruction,payload):
        if instruction.startswith('REVIEW') and self.mode=='review_timeout':
            raise RuntimeError('timeout')
        if instruction.startswith('REVIEW') and self.mode=='review_skip':
            return {'decision':'no_action','reason':'이미 해결됨','candidates':[]}
        if instruction.startswith('TRIAGE'):
            return {'decision':'no_action' if self.mode=='skip' else 'reply','target_ts':'20.0','reason':'본인에게 온 요청'}
        return {'decision':'reply','style_summary':'존댓말과 확인 표현','candidates':[
            {'text':text,'intent':'확인','evidence_ts':['20.0'],'style_ts':['10.0' if self.mode!='bad_source' else '11.0']}
            for text in ['평가표에서 확인할 범위를 알려주실 수 있을까요?','어떤 모델의 비교가 필요한지 확인 부탁드립니다!','평가표의 누락 항목을 먼저 확인하면 될까요?']]}
class Tests(unittest.IsolatedAsyncioTestCase):
    async def generate(self,mode='reply'):
        gateway=Gateway()
        state=await build_app(gateway,Model(mode)).ainvoke({'user':'UME','channel':'CTEST'})
        return gateway,state
    def test_only_own_past_messages(self):
        profile=own_examples(HISTORY,'UME',THREAD)
        self.assertEqual([m['ts'] for m in profile['examples']],['10.0'])
        self.assertEqual(profile['confidence'],'limited')
    def test_empty_profile(self):
        self.assertEqual(own_examples([],'UME',THREAD)['sample_count'],0)
    def test_normalization_drops_bots(self):
        result=normalize({'messages':[{'user':'UME','ts':'1','text':'hello'},{'user':'BOT','bot_id':'B1','ts':'2','text':'bot'}]}, {})
        self.assertEqual(len(result),1)
    async def test_no_send_without_selection(self):
        gateway,state=await self.generate()
        self.assertEqual(len(state['candidates']),3)
        self.assertEqual(gateway.sent,[])
    async def test_irrelevant_thread_skips(self):
        gateway,state=await self.generate('skip')
        self.assertEqual(state['decision'],'no_action'); self.assertEqual(gateway.reads,['recent'])
    async def test_review_failure_locks_send(self):
        gateway,state=await self.generate('review_timeout')
        self.assertEqual(state['decision'],'needs_review')
        with self.assertRaises(ValueError): await approve_and_send(gateway,state,0,state['candidates'][0]['text'])
        self.assertEqual(gateway.sent,[])
    async def test_review_can_cancel_reply(self):
        gateway,state=await self.generate('review_skip')
        self.assertEqual(state['decision'],'no_action')
        self.assertEqual(state['candidates'],[])
        self.assertEqual(gateway.sent,[])
    async def test_fabricated_style_source_rejected(self):
        with self.assertRaises(ValueError): await self.generate('bad_source')
    async def test_selected_candidate_only_and_no_duplicate(self):
        gateway,state=await self.generate()
        text=state['candidates'][1]['text']
        await approve_and_send(gateway,state,1,text)
        self.assertEqual(gateway.sent,[text])
        with self.assertRaises(ValueError): await approve_and_send(gateway,state,1,text)
    async def test_changed_context_requires_regeneration(self):
        gateway,state=await self.generate()
        gateway.messages.append({'user':'UME','ts':'22.0','text':'이미 처리했습니다.','thread_ts':'20.0'})
        with self.assertRaises(ValueError): await approve_and_send(gateway,state,0,state['candidates'][0]['text'])
        self.assertEqual(gateway.sent,[])
    async def test_wrong_approval_text_rejected(self):
        gateway,state=await self.generate()
        with self.assertRaises(ValueError): await approve_and_send(gateway,state,0,'다른 문구')
        self.assertEqual(gateway.sent,[])
if __name__=='__main__': unittest.main()
