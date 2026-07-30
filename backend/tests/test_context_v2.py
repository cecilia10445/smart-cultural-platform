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
