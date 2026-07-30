from __future__ import annotations
from .models import ContextBudget, ContextFact, ContextSummaryV2, FactSource
def estimate_tokens(value): return max(1, (len(str(value).encode('utf-8'))+2)//3)
class DeterministicContextSummarizer:
    async def summarize(self, previous_summary, messages, session_state):
        summary=previous_summary.model_copy(deep=True) if previous_summary else ContextSummaryV2(session_id=str(session_state['id']))
        summary.source_message_count += len(messages)
        if messages:
            summary.source_message_start_id=summary.source_message_start_id or str(messages[0]['id']); summary.source_message_end_id=str(messages[-1]['id'])
            users=[m for m in messages if m.get('role')=='user']
            if users and not summary.user_goal: summary.user_goal=ContextFact(value=str(users[0].get('content_text',''))[:300],source_type=FactSource.USER_CONFIRMED,source_message_ids=[str(users[0]['id'])],confidence=1)
            for m in users:
                text=str(m.get('content_text',''))
                if '不要' in text and text not in [x.value for x in summary.rejected_directions]: summary.rejected_directions.append(ContextFact(value=text[:200],source_type=FactSource.USER_CONFIRMED,source_message_ids=[str(m['id'])],confidence=1))
        summary.conversation_summary=(summary.user_goal.value if summary.user_goal else 'Session design context')[:500]
        return summary
class RuntimeContextBuilder:
    def __init__(self, repository, budget=None, summarizer=None): self.repository=repository; self.budget=budget or ContextBudget(); self.summarizer=summarizer or DeterministicContextSummarizer()
    async def build(self,user_id,session_id,current_input):
        session,messages,_=self.repository.get_detail_rows(session_id,user_id); recent=messages[-self.budget.max_recent_messages:]; total=estimate_tokens(messages)+estimate_tokens(current_input)
        return {'session_state': {'id':session['id'],'status':session['status']}, 'context_summary':None,'recent_messages':[{'role':m['role'],'text':m['content_text'][:1000]} for m in recent], 'current_user_input':current_input,'estimated_tokens_before':total,'compression_triggered':total>self.budget.compression_trigger_tokens or len(messages)>self.budget.compression_trigger_messages}
