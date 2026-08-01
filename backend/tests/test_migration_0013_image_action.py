import importlib.util
from pathlib import Path
def test_0013_contract_is_additive(monkeypatch):
    path=Path(__file__).parents[1]/"migrations"/"versions"/"0013_agent_image_action_execution.py"; spec=importlib.util.spec_from_file_location("m",path); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    calls=[]
    for name in ("add_column","create_index"): monkeypatch.setattr(m.op,name,lambda *args,_name=name,**kwargs:calls.append((_name,args)))
    m.upgrade()
    assert (m.revision,m.down_revision)==("0013","0012") and {args[1].name for kind,args in calls if kind=="add_column"}=={"external_outcome_status","provider_request_id"}
