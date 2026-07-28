"""Injectable, single Round 17C core used by fake and real entry points."""
from __future__ import annotations
import hashlib, json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from evaluation.round17c_judge import extract_promptfoo_jobs, normalize_judge_results
from evaluation.round17c_runner import BRIEF_PAYLOAD, freeze_evidence, run_baseline, run_guided_plan, run_guided_final, sanitized_model_error

def _now(): return datetime.now(timezone.utc).isoformat().replace('+00:00','Z')
def _write(p:Path,v:Any): p.parent.mkdir(parents=True,exist_ok=True); p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
def _hash(p:Path): return hashlib.sha256(p.read_bytes()).hexdigest()
def _seal(root:Path,name:str):
    files=sorted(x.relative_to(root).as_posix() for x in root.rglob('*') if x.is_file() and x.name!=name); _write(root/name,{'required_files':files,'sha256':{f:_hash(root/f) for f in files}})
def _verify(root:Path,name:str):
    s=json.loads((root/name).read_text()); return sorted(x.relative_to(root).as_posix() for x in root.rglob('*') if x.is_file() and x.name!=name)==s['required_files'] and all(_hash(root/f)==h for f,h in s['sha256'].items())
def execute_round17c(config:dict[str,Any],qwen_client_factory:Callable[[],Any],promptfoo_executor:Callable[[Path,dict[str,Any]],dict[str,Any]],artifact_root:Path, qwen_wire:dict[str,Any]|None=None)->Path:
    rid=config['run_id']; run=artifact_root/rid; run.mkdir(parents=True,exist_ok=False); g,e=run/'generation',run/'evaluation'; calls={'qwen':0,'deepseek':0,'image':0,'database_writes':0}; events=[]
    def sync_qwen():
      if qwen_wire is not None: calls['qwen']=int(qwen_wire.get('requests',0))
    def st(name,fn):
      if qwen_wire is not None: qwen_wire['stage']=name
      try: r=fn(); events.append({'stage':name,'status':'completed','utc':_now()}); return r
      except Exception as x: events.append({'stage':name,'status':'failed','stable_error':getattr(x,'code',type(x).__name__),'utc':_now()}); raise
      finally: sync_qwen()
    try:
      _write(g/'effective-config.json',config); _write(g/'brief.json',BRIEF_PAYLOAD); frozen=st('freeze_evidence',lambda:freeze_evidence(BRIEF_PAYLOAD['brief'])); _write(g/'frozen-evidence.json',frozen); model=qwen_client_factory()
      a=st('baseline',lambda:run_baseline(model,BRIEF_PAYLOAD['brief'],frozen)); calls['qwen']+=a[1]['requests'] if qwen_wire is None else 0; _write(g/'baseline-result.json',{'output':a[0].model_dump(),'metrics':a[1]}); _write(g/'qwen-attempt-baseline.json',{'stage':'baseline','ordinal':calls['qwen'],'requests':a[1]['requests'],'retries':0})
      d,p,pm=st('guided_planner',lambda:run_guided_plan(model,BRIEF_PAYLOAD['brief'],frozen)); calls['qwen']+=pm['requests'] if qwen_wire is None else 0; _write(g/'guided-plan.json',{'receipt':p,'metrics':pm}); _write(g/'tool-trajectory.json',pm['tool_trajectory']); _write(g/'qwen-attempt-guided-planner.json',{'stage':'guided_planner','ordinal':calls['qwen'],'requests':pm['requests'],'retries':0})
      b=st('guided_final',lambda:run_guided_final(model,BRIEF_PAYLOAD['brief'],frozen,d)); calls['qwen']+=b[1]['requests'] if qwen_wire is None else 0; _write(g/'guided-result.json',{'output':b[0].model_dump(),'metrics':b[1]}); _write(g/'qwen-attempt-guided-final.json',{'stage':'guided_final','ordinal':calls['qwen'],'requests':b[1]['requests'],'retries':0})
      if calls['qwen']>5: raise RuntimeError('QWEN_BUDGET_EXCEEDED')
      inputs={'brief':BRIEF_PAYLOAD['brief'],'arms':{'baseline':a[0].model_dump(),'skill_guided':b[0].model_dump()}}; _write(g/'judge-inputs.json',inputs); _write(g/'qwen-request-events.json',(qwen_wire or {}).get('attempts',[])); _write(g/'stage-events.json',events); _seal(g,'generation-seal.json')
      prompts={};
      for job,body in {'individual-baseline':{'candidate':inputs['arms']['baseline']},'individual-guided':{'candidate':inputs['arms']['skill_guided']},'pairwise-ab':{'candidate_0':inputs['arms']['baseline'],'candidate_1':inputs['arms']['skill_guided']},'pairwise-ba':{'candidate_0':inputs['arms']['skill_guided'],'candidate_1':inputs['arms']['baseline']}}.items():
        text=json.dumps({'brief':inputs['brief'],**body},ensure_ascii=False,sort_keys=True); prompts[job]={'prompt':text,'sha256':hashlib.sha256(text.encode()).hexdigest(),'identity_leak':any(z in text for z in ('baseline','skill_guided'))}
      _write(e/'judge-prompt-manifest.json',prompts); _write(e/'candidate-mapping.json',{'ab':{'candidate_0':'baseline','candidate_1':'skill_guided'},'ba':{'candidate_0':'skill_guided','candidate_1':'baseline'}})
      pf=st('promptfoo',lambda:promptfoo_executor(g,prompts)); calls['deepseek']=len(pf['attempts']); _write(e/'promptfoo-results.json',pf); raw=extract_promptfoo_jobs({'results':pf['results']}); _write(e/'judge-raw-results.json',raw); norm=st('judge_normalization',lambda:normalize_judge_results(raw['individual-baseline'],raw['individual-guided'],raw['pairwise-ab'],raw['pairwise-ba'])); _write(e/'judge-parsed-results.json',norm)
      report={'technical_status':'completed','evaluation_validity':norm['evaluation_validity'],'winner':norm['winner'],'arms':{'baseline':{**a[0].model_dump(),**a[1],'dimensions':norm['individual']['baseline'].get('dimensions',{})},'skill_guided':{**b[0].model_dump(),**b[1],'dimensions':norm['individual']['skill_guided'].get('dimensions',{}),'tool_trajectory':pm['tool_trajectory']}}}; _write(e/'normalized-report.json',report); (e/'report.html').write_text('<pre>'+json.dumps(report,ensure_ascii=False)+'</pre>',encoding='utf8'); _seal(e,'evaluation-seal.json'); _write(run/'manifest.json',{'run_id':rid,'technical_status':'completed','evaluation_validity':norm['evaluation_validity'],'actual_calls':calls,'finished_at':_now()}); _seal(run,'run-seal.json'); return run
    except Exception as x:
      sync_qwen()
      attempts=(qwen_wire or {}).get('attempts',[])
      if attempts:
        _write(g/'qwen-request-events.json',attempts)
        _write(g/'model-error.json',sanitized_model_error(x,stage=events[-1]['stage'] if events else 'configuration',model_name=config.get('qwen',{}).get('model','unknown'),request_ordinal=calls['qwen'],request_shape_hash=attempts[-1].get('request_shape_sha256')))
      _write(run/'unsealed-failure.json',{'failure_stage':events[-1]['stage'] if events else 'configuration','stable_error':getattr(x,'code',type(x).__name__),'actual_calls':calls,'events':events}); _write(run/'manifest.json',{'run_id':rid,'technical_status':'failed','evaluation_validity':'not_run','actual_calls':calls}); _seal(run,'run-seal.json'); return run
