import asyncio
from backend.agents.context import RuntimeContextBuilder, DeterministicContextSummarizer, FactSource

def test_deterministic_summary_preserves_goal_and_rejection():
    state={'id':'s'}; messages=[{'id':'1','role':'user','content_text':'设计敦煌书签'}, {'id':'2','role':'user','content_text':'不要仿古'}]
    summary=asyncio.run(DeterministicContextSummarizer().summarize(None,messages,state))
    assert summary.user_goal.source_type is FactSource.USER_CONFIRMED
    assert summary.rejected_directions[0].value=='不要仿古'

class Repo:
 def get_detail_rows(self,*_): return {'id':'s','status':'created'}, [{'id':str(i),'role':'user','content_text':'x'*100} for i in range(13)], []
def test_budget_triggers_compression_without_mutating_messages():
 built=asyncio.run(RuntimeContextBuilder(Repo()).build('u','s','now'))
 assert built['compression_triggered'] and len(built['recent_messages'])==10


class LongSessionRepo:
 def __init__(self): self.messages={}; self.summaries={}; self.versions={}
 def get_detail_rows(self, session_id, user_id):
  return {'id':session_id,'status':'created','text_revision_count':0}, list(self.messages.get(session_id,[])), []
 def get_active_summary(self, user_id, session_id): return self.summaries.get(session_id)
 def get_messages_after_summary(self, user_id, session_id, end_id):
  rows=self.messages.get(session_id,[])
  return rows if not end_id else [row for row in rows if int(row['id'].split('-')[-1]) > int(end_id.split('-')[-1])]
 def create_summary_version(self, user_id, session_id, summary):
  version=self.versions.get(session_id,0)+1; self.versions[session_id]=version
  record={'id':f'{session_id}-summary-{version}','session_version':version,'summary':summary.model_dump(mode='json')}
  self.summaries[session_id]=record
  return record


def test_fifteen_turn_context_is_incremental_and_session_scoped_offline():
 repo=LongSessionRepo(); builder=RuntimeContextBuilder(repo)
 turns=[
  '设计敦煌主题书签，服务博物馆访客。','使用场景是旅行阅读。','风格必须现代简约。','不要过度仿古。',
  '材质倾向磨砂金属。','拒绝大红色配色。','确认受众是年轻旅行者。','受众改为青年阅读爱好者。',
  '请查询文化资料。','如果没有资料可按纯创意方向继续。','加载设计方法。','提出候选 Brief。',
  '材质改为磨砂金属与纸质夹层。','再次校验约束。','请生成最终纯文本 Brief。',
 ]
 for index,text in enumerate(turns,1):
  repo.messages.setdefault('session-a',[]).append({'id':f'a-{index}','role':'user','message_type':'runtime_request','content_text':text})
  payload=asyncio.run(builder.build('owner','session-a',text))
  assert payload['estimated_tokens_after'] >= 1
 assert repo.versions['session-a'] >= 2
 summary=repo.summaries['session-a']['summary']
 assert summary['user_goal']['value'].startswith('设计敦煌主题书签')
 assert any('不要过度仿古' in item['value'] for item in summary['rejected_directions'])
 repo.messages['session-b']=[{'id':'b-1','role':'user','message_type':'runtime_request','content_text':'设计苗绣帆布包'}]
 second=asyncio.run(builder.build('owner','session-b','设计苗绣帆布包'))
 assert second['context_summary'] is None and all('敦煌' not in row['text'] for row in second['recent_messages'])
