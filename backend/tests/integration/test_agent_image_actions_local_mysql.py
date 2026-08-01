"""Opt-in localhost-only F3.1 verification; never accepts an arbitrary database."""
from __future__ import annotations
import json, os, re, threading, uuid
from datetime import datetime
from urllib.parse import urlparse

import pymysql, pytest, sqlalchemy as sa
from alembic import command
from alembic.config import Config

from backend.agents.actions.executor import AgentActionExecutor
from backend.domain.agent_design_domain import ActionStatus, ActionType, canonical_json_hash
from backend.services.agent_design_domain_repository import AgentDesignDomainRepository
from backend.services.agent_image_generation import ImageGenerationResult

PATTERN=re.compile(r"^aigc_platform_agent_f3_test_[0-9]{14}$")

def _url():
    value=os.getenv("AGENT_F3_TEST_DATABASE_URL")
    if os.getenv("RUN_MYSQL_INTEGRATION")!="1" or not value: pytest.skip("requires explicit local F3 test database")
    parsed=urlparse(value); database=parsed.path.lstrip("/")
    if parsed.hostname not in {"localhost","127.0.0.1"} or not PATTERN.fullmatch(database): raise RuntimeError("unsafe local F3 test database")
    return value, parsed, database

class _Service:
    def __init__(self,p): self.p=p
    def _borrow_connection(self): return pymysql.connect(host=self.p.hostname,port=self.p.port or 3306,user=self.p.username,password=self.p.password,database=self.p.path.lstrip('/'),charset="utf8mb4",autocommit=False)
class _Fake:
    def __init__(self,fail=False,gate=None): self.calls=0; self.fail=fail; self.gate=gate
    def generate(self,request):
        self.calls+=1
        if self.gate: self.gate.wait(5)
        if self.fail: raise RuntimeError("fake image failure")
        return ImageGenerationResult(f"mock://f3/{self.calls}",request.presentation_mode,f"fake-{self.calls}")
def _snap(kind,sid,tid,parent=None):
    value={"source_type":kind,"source_session_id":sid,"source_task_id":tid,"source_runtime_run_id":None,"source_message_ids":["m"],"source_artifact_ids":[],"parent_image_artifact_id":parent,"confirmed_constraints":["test constraint"],"tentative_assumptions":["test assumption"],"positive_prompt":"safe test prompt","negative_prompt":"no text","presentation_mode":"single_hero","provider_options":{}}
    value["snapshot_hash"]=canonical_json_hash(value); return value
def _seed(engine,kind,snapshot,state="approved"):
    sid,tid,aid=str(uuid.uuid4()),str(uuid.uuid4()),str(uuid.uuid4()); now=datetime.now()
    with engine.begin() as c:
        c.execute(sa.text("INSERT INTO agent_sessions (id,user_id,status,current_stage,text_revision_count,version,created_at,updated_at,conversation_status) VALUES (:id,'f31','completed','completed',0,1,:n,:n,'active')"),{"id":sid,"n":now})
        c.execute(sa.text("INSERT INTO agent_design_tasks (id,user_id,session_id,title,status,origin,version,created_at,updated_at) VALUES (:id,'f31',:s,'F3 test','active','native',1,:n,:n)"),{"id":tid,"s":sid,"n":now})
        c.execute(sa.text("INSERT INTO agent_actions (id,user_id,session_id,task_id,action_type,status,idempotency_key,request_hash,proposal_snapshot_json,approval_snapshot_json,created_at,updated_at,approved_at) VALUES (:id,'f31',:s,:t,:k,:st,:key,:hash,:p,'{}',:n,:n,:n)"),{"id":aid,"s":sid,"t":tid,"k":kind,"st":state,"key":"request-"+aid,"hash":"0"*64,"p":json.dumps(snapshot),"n":now})
    return sid,tid,aid

def test_f31_local_mysql_lifecycle_and_fake_image_provider():
    url,p,database=_url(); previous=os.environ.get("MIGRATION_DATABASE_URL"); os.environ["MIGRATION_DATABASE_URL"]=url
    engine=sa.create_engine(url,hide_parameters=True); config=Config("alembic.ini")
    try:
        command.upgrade(config,"0012"); command.upgrade(config,"0013")
        assert {"external_outcome_status","provider_request_id"} <= {x["name"] for x in sa.inspect(engine).get_columns("agent_actions")}
        sentinel={"user_id":"f31-sentinel","event_type":"generate","timestamp":datetime.now(),"prompt":"sentinel","style":"test","image_url":"mock://sentinel","title":"sentinel","content":"sentinel","generation_time":0,"content_length":8,"data_origin":"test"}
        with engine.begin() as c:
            result=c.execute(sa.text("INSERT INTO generation_logs (user_id,event_type,timestamp,prompt,style,image_url,title,content,generation_time,content_length,download_count,data_origin) VALUES (:user_id,:event_type,:timestamp,:prompt,:style,:image_url,:title,:content,:generation_time,:content_length,0,:data_origin)"),sentinel); sentinel_id=result.lastrowid
        baseline=engine.connect().execute(sa.text("SELECT COUNT(*) FROM generation_logs")).scalar_one()
        repo=AgentDesignDomainRepository(_Service(p)); fake=_Fake(); sid,tid,a1=_seed(engine,ActionType.GENERATE_IMAGE_FROM_CONVERSATION.value,{})
        with engine.begin() as c:c.execute(sa.text("UPDATE agent_actions SET proposal_snapshot_json=:p WHERE id=:id"),{"p":json.dumps(_snap("conversation_snapshot",sid,tid)),"id":a1})
        first,replay=AgentActionExecutor(repo,fake).execute("f31",a1,idempotency_key="e1",expected_action_status="approved",expected_task_version=1)
        assert not replay and first.status is ActionStatus.COMPLETED and fake.calls==1 and first.generation_log_id
        again,replay=AgentActionExecutor(repo,fake).execute("f31",a1,idempotency_key="e1",expected_action_status="approved",expected_task_version=1)
        assert replay and again.generation_log_id==first.generation_log_id and fake.calls==1
        with pytest.raises(Exception,match="ACTION_EXECUTION_IDEMPOTENCY_CONFLICT"):
            AgentActionExecutor(repo,fake).execute("f31",a1,idempotency_key="e1",expected_action_status="approved",expected_task_version=2)
        with engine.connect() as c: parent=c.execute(sa.text("SELECT id FROM agent_artifacts WHERE source_action_id=:id"),{"id":a1}).scalar_one()
        _,_,a2=_seed(engine,ActionType.REGENERATE_IMAGE.value,{})
        with engine.begin() as c:c.execute(sa.text("UPDATE agent_actions SET session_id=:s,task_id=:t,proposal_snapshot_json=:p WHERE id=:id"),{"s":sid,"t":tid,"p":json.dumps(_snap("regeneration_snapshot",sid,tid,parent)),"id":a2})
        second,_=AgentActionExecutor(repo,fake).execute("f31",a2,idempotency_key="e2",expected_action_status="approved",expected_task_version=1)
        assert second.status is ActionStatus.COMPLETED and fake.calls==2
        with engine.connect() as c:
            assert c.execute(sa.text("SELECT parent_artifact_id FROM agent_artifacts WHERE source_action_id=:id"),{"id":a2}).scalar_one()==parent
            assert c.execute(sa.text("SELECT COUNT(*) FROM generation_logs")).scalar_one()==baseline+2
            assert c.execute(sa.text("SELECT status FROM agent_sessions WHERE id=:id"),{"id":sid}).scalar_one()=="completed"
            assert c.execute(sa.text("SELECT status FROM agent_design_tasks WHERE id=:id"),{"id":tid}).scalar_one()=="active"
        sid3,tid3,a3=_seed(engine,ActionType.GENERATE_IMAGE_FROM_CONVERSATION.value,{})
        with engine.begin() as c:c.execute(sa.text("UPDATE agent_actions SET proposal_snapshot_json=:p WHERE id=:id"),{"p":json.dumps(_snap("conversation_snapshot",sid3,tid3)),"id":a3})
        failure=_Fake(True)
        with pytest.raises(RuntimeError): AgentActionExecutor(repo,failure).execute("f31",a3,idempotency_key="bad",expected_action_status="approved",expected_task_version=1)
        assert failure.calls==1
        with engine.connect() as c: assert c.execute(sa.text("SELECT status FROM agent_actions WHERE id=:id"),{"id":a3}).scalar_one()=="failed"
        sid4,tid4,a4=_seed(engine,ActionType.GENERATE_IMAGE_FROM_CONVERSATION.value,{},"running")
        with engine.begin() as c:c.execute(sa.text("UPDATE agent_actions SET proposal_snapshot_json=:p,external_outcome_status='unknown_outcome' WHERE id=:id"),{"p":json.dumps(_snap("conversation_snapshot",sid4,tid4)),"id":a4})
        no_call=_Fake()
        with pytest.raises(Exception,match="ACTION_EXECUTION_RECOVERY_REQUIRED"): AgentActionExecutor(repo,no_call).execute("f31",a4,idempotency_key="unknown",expected_action_status="approved",expected_task_version=1)
        assert no_call.calls==0
        with pytest.raises(RuntimeError): command.downgrade(config,"0012")
        with engine.begin() as c:
            assert c.execute(sa.text("SELECT image_url FROM generation_logs WHERE id=:id"),{"id":sentinel_id}).scalar_one()=="mock://sentinel"
            c.execute(sa.text("DELETE FROM agent_artifacts WHERE user_id='f31' AND parent_artifact_id IS NOT NULL"))
            c.execute(sa.text("DELETE FROM agent_artifacts WHERE user_id='f31'"))
            c.execute(sa.text("UPDATE agent_actions SET generation_log_id=NULL WHERE user_id='f31'"))
            c.execute(sa.text("DELETE FROM agent_actions WHERE user_id='f31'")); c.execute(sa.text("DELETE FROM generation_logs WHERE user_id='f31'")); c.execute(sa.text("DELETE FROM agent_design_tasks WHERE user_id='f31'")); c.execute(sa.text("DELETE FROM agent_sessions WHERE user_id='f31'"))
        command.downgrade(config,"0012"); command.upgrade(config,"0013")
    finally:
        engine.dispose()
        if previous is None: os.environ.pop("MIGRATION_DATABASE_URL",None)
        else: os.environ["MIGRATION_DATABASE_URL"]=previous
