from __future__ import annotations
import json
from types import SimpleNamespace
from evaluation import round17c_orchestrator as o
from evaluation.round17c_contract import Round17CFinalOutput

def _out(tag): return Round17CFinalOutput(product_copy=f"清韵折叠阅读灯{tag}以竹木与纸罩提供稳定阅读光线，适合书房与旅行。",image_design_spec=f"折叠阅读灯{tag}采用竹木纹理与半透明纸罩，突出展开和收纳关系。",used_source_ids=['s1'])
def _raw(w): return json.dumps({'winner_index':w,'winner_candidate_id':f'candidate_{w}','final_reason':f'candidate_{w} wins'})
def test_same_orchestrator_reaches_final_seal_comparable(monkeypatch,tmp_path):
  frozen={'status':'grounded','sources':[{'source_id':'s1'}]}; monkeypatch.setattr(o,'freeze_evidence',lambda _:frozen); monkeypatch.setattr(o,'run_baseline',lambda *a:(_out('A'),{'requests':1,'latency_ms':1})); deps=SimpleNamespace(loaded_skill_body='x'); monkeypatch.setattr(o,'run_guided_plan',lambda *a:(deps,{'skill_id':'x'},{'requests':1,'tool_trajectory':[{'tool':'load_generation_skill'}]})); monkeypatch.setattr(o,'run_guided_final',lambda *a:(_out('B'),{'requests':1,'latency_ms':1}))
  def pf(_g,p):
    rows=[]
    for job in p: rows.append({'metadata':{'round17c_judge_job':job},'response':{'output': json.dumps({'dimensions':{k:{'score':4,'reason':'ok'} for k in __import__('evaluation.round17c_judge',fromlist=['DIMENSIONS']).DIMENSIONS},'final_reason':'ok'}) if job.startswith('individual') else _raw(0 if job=='pairwise-ab' else 1)}})
    return {'attempts':[{'job':x} for x in p],'results':{'results':rows}}
  run=o.execute_round17c({'run_id':'round-17c-clean-20260728T000000Z-offline'},lambda:object(),pf,tmp_path)
  assert (run/'run-seal.json').exists(); assert json.loads((run/'evaluation/normalized-report.json').read_text())['winner']=='baseline'

def test_same_orchestrator_position_bias(monkeypatch,tmp_path):
  frozen={'status':'grounded','sources':[{'source_id':'s1'}]}; monkeypatch.setattr(o,'freeze_evidence',lambda _:frozen); monkeypatch.setattr(o,'run_baseline',lambda *a:(_out('A'),{'requests':1})); deps=SimpleNamespace(loaded_skill_body='x'); monkeypatch.setattr(o,'run_guided_plan',lambda *a:(deps,{'skill_id':'x'},{'requests':1,'tool_trajectory':[{'tool':'load_generation_skill'}]})); monkeypatch.setattr(o,'run_guided_final',lambda *a:(_out('B'),{'requests':1}))
  def pf(_g,p):
    dims={k:{'score':4,'reason':'ok'} for k in __import__('evaluation.round17c_judge',fromlist=['DIMENSIONS']).DIMENSIONS}; rows=[{'metadata':{'round17c_judge_job':j},'response':{'output':json.dumps({'dimensions':dims,'final_reason':'ok'}) if j.startswith('individual') else _raw(1)}} for j in p]; return {'attempts':[{}]*4,'results':{'results':rows}}
  run=o.execute_round17c({'run_id':'round-17c-clean-20260728T000001Z-offline'},lambda:object(),pf,tmp_path); report=json.loads((run/'evaluation/normalized-report.json').read_text()); assert report['evaluation_validity']=='inconclusive_position_bias' and report['winner'] is None
