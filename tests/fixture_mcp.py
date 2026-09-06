"""Synthetic Slack-shaped MCP server for transport testing. Never accesses Slack."""
from mcp.server.fastmcp import FastMCP
mcp=FastMCP('Synthetic Slack test server')
HISTORY=[
 {'user':'UOTHER','ts':'10.0','text':'야 빨리 보내'},
 {'user':'UME','ts':'11.0','text':'교수님, 평가 기준을 먼저 확인해 보면 좋을 것 같습니다!'},
 {'user':'UME','ts':'12.0','text':'확인했습니다! 누락된 항목을 정리해서 공유드리겠습니다.'},
 {'user':'UME','ts':'13.0','text':'제가 이해한 방향이 맞는지 확인 부탁드립니다.'},
]
THREAD=[{'user':'UPROF','ts':'20.0','text':'<@UME> 평가 결과표에 모델별 비교가 빠진 것 같은데 확인 가능한가요?'}]
@mcp.tool()
def test_recent(channel:str)->dict: return {'messages':THREAD}
@mcp.tool()
def test_search(query:str)->dict: return {'messages':{'matches':HISTORY}}
@mcp.tool()
def test_thread(channel:str,ts:str)->dict: return {'messages':THREAD}
@mcp.tool()
def test_send(channel:str,ts:str,text:str)->dict: return {'ok':True,'simulated':True,'text':text}
if __name__=='__main__': mcp.run()
