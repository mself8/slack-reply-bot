"""MCP transport and explicit Slack tool bindings; no Slack Web API calls."""
from contextlib import asynccontextmanager
from datetime import timedelta
import json
import os

from jsonschema import validate
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamablehttp_client


def unpack(result):
    if result.isError:
        raise RuntimeError('MCP 도구가 오류를 반환했습니다. 연결·권한·인자를 확인하세요.')
    if result.structuredContent is not None:
        return result.structuredContent
    for item in result.content:
        if getattr(item,'type',None) == 'text':
            try: return json.loads(item.text)
            except ValueError: continue
    raise ValueError('구조화된 JSON 응답이 필요합니다. 이 서버에 맞는 응답 어댑터를 설정하세요.')


def dig(data, path):
    for part in path.split('.') if path else []:
        data = data[int(part)] if isinstance(data,list) else data[part]
    return data


def normalize(data, binding):
    rows = dig(data,binding.get('result_path','messages'))
    if not isinstance(rows,list): raise ValueError('메시지 결과가 목록이 아닙니다.')
    fields = binding.get('fields',{})
    messages=[]
    for row in rows:
        if not isinstance(row,dict) or row.get('bot_id') or row.get('subtype'): continue
        msg={}
        for key in ('user','text','ts','thread_ts'):
            try: msg[key]=dig(row,fields.get(key,key))
            except (KeyError,TypeError): msg[key]=''
        if not all(isinstance(msg[k],str) and msg[k] for k in ('user','text','ts')): continue
        if len(msg['text'])>12000: msg['text']=msg['text'][:12000]
        messages.append(msg)
    return sorted(messages,key=lambda m:float(m['ts']))


class SlackMCP:
    def __init__(self,session,bindings,schemas):
        self.session=session
        self.bindings=bindings
        self.schemas=schemas
        self.calls=[]

    async def call(self,operation,**values):
        binding=self.bindings[operation]
        name=binding['tool']
        args={k:(values[v[1:]] if isinstance(v,str) and v.startswith('$') else v)
              for k,v in binding.get('arguments',{}).items()}
        validate(args,self.schemas[name])
        self.calls.append({'operation':operation,'tool':name})
        data=unpack(await self.session.call_tool(name,args))
        if isinstance(data,dict) and data.get('ok') is False:
            raise RuntimeError(f'MCP {operation} 요청 실패')
        return normalize(data,binding) if operation!='send' else data

    async def recent(self,channel): return await self.call('recent',channel=channel)
    async def history(self,channel,user):
        return await self.call('history',channel=channel,user=user,query=f'from:<@{user}> in:<#{channel}>')
    async def thread(self,channel,ts): return await self.call('thread',channel=channel,ts=ts)
    async def send(self,channel,ts,text): return await self.call('send',channel=channel,ts=ts,text=text)


@asynccontextmanager
async def connect(config):
    connection=config['connection']
    if connection['transport']=='stdio':
        env={key:os.environ[key] for key in connection.get('env_names',[]) if key in os.environ}
        params=StdioServerParameters(command=connection['command'],args=connection.get('args',[]),env=env)
        transport=stdio_client(params)
    elif connection['transport']=='http':
        headers={key:os.environ[env_name] for key,env_name in connection.get('header_env',{}).items()}
        transport=streamablehttp_client(connection['url'],headers=headers)
    else: raise ValueError('transport는 stdio 또는 http여야 합니다.')
    async with transport as streams:
        async with ClientSession(streams[0],streams[1],read_timeout_seconds=timedelta(seconds=45)) as session:
            await session.initialize()
            schemas={}
            cursor=None
            while True:
                listing=await session.list_tools(cursor=cursor)
                schemas.update({tool.name:tool.inputSchema for tool in listing.tools})
                cursor=listing.nextCursor
                if not cursor: break
            for operation,binding in config.get('bindings',{}).items():
                if operation not in {'recent','history','thread','send'}: raise ValueError('알 수 없는 연동 작업')
                if binding['tool'] not in schemas: raise ValueError(f'MCP 서버에 도구가 없습니다: {binding["tool"]}')
            yield SlackMCP(session,config.get('bindings',{}),schemas)
