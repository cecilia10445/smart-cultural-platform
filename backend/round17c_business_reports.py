"""Fail-closed, read-only DTOs for experimental business generation artifacts."""
from __future__ import annotations
import hashlib, json, re
from pathlib import Path
from typing import Any

RUN_ID = re.compile(r"^round-17c-business-[0-9]{8}T[0-9]{6}Z-[A-Za-z0-9_-]{7,40}$")

class BusinessReportUnavailable(ValueError): pass

def _json(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 10*1024*1024: raise BusinessReportUnavailable("REPORT_UNAVAILABLE")
    value=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value,dict): raise BusinessReportUnavailable("REPORT_UNAVAILABLE")
    return value

def _dir(root: Path, run_id: str) -> Path:
    root=root.resolve(); path=root/run_id
    if not RUN_ID.fullmatch(run_id) or path.is_symlink() or not path.is_dir() or path.resolve().parent != root: raise BusinessReportUnavailable("REPORT_UNAVAILABLE")
    return path

def _verified(path: Path) -> bool:
    try:
        seal=_json(path/'sha256sums.json'); required=seal['required_files']; sums=seal['sha256']
        actual={p.name for p in path.iterdir() if p.is_file() and p.name!='sha256sums.json'}
        return seal.get('inventory_version')==1 and set(required)==actual==set(sums) and all(isinstance(v,str) and re.fullmatch(r'[0-9a-f]{64}',v) and hashlib.sha256((path/k).read_bytes()).hexdigest()==v for k,v in sums.items())
    except Exception: return False

def public_business_run(root: Path, run_id: str) -> dict[str, Any]:
    path=_dir(root,run_id); manifest=_json(path/'manifest.json'); integrity='verified' if _verified(path) else 'failed'
    base={'run_id':run_id,'started_at':manifest.get('started_at'),'technical_status':manifest.get('technical_status'),'integrity_status':integrity,'failure_stage':manifest.get('failure_stage'),'stable_error':manifest.get('stable_error')}
    if integrity!='verified' or manifest.get('technical_status')!='completed': return {**base,'report':None}
    report=_json(path/'normalized-report.json'); output=report.get('output')
    if not isinstance(output,dict) or not all(isinstance(output.get(k),str) and output[k] for k in ('product_copy','image_design_spec')): raise BusinessReportUnavailable('REPORT_UNAVAILABLE')
    return {**base,'report':{k:report.get(k) for k in ('created_at','rag_status','source_ids','selected_skill_id','skill_version','skill_body_sha256','tool_trajectory','planner_latency_ms','final_latency_ms','actual_calls','business_record_id','database_transaction_status')},'output':{'product_copy':output['product_copy'],'image_design_spec':output['image_design_spec'],'used_source_ids':output.get('used_source_ids',[])}}

def list_business_runs(root: Path) -> list[dict[str,Any]]:
    if not root.exists() or root.is_symlink(): return []
    values=[]
    for path in root.iterdir():
        if path.is_dir() and not path.is_symlink() and RUN_ID.fullmatch(path.name):
            try:
                item=public_business_run(root,path.name); values.append({k:item[k] for k in ('run_id','started_at','technical_status','integrity_status')})
            except (OSError,ValueError,json.JSONDecodeError): values.append({'run_id':path.name,'started_at':None,'technical_status':'failed','integrity_status':'failed'})
    return sorted(values,key=lambda x:x['started_at'] or '',reverse=True)
