"""Offline deterministic harness for CulturalProductBrief contract cases."""
import argparse, json
from pathlib import Path

from backend.domain.cultural_product_brief import BriefValidationError, validate_cultural_product_request
from backend.prompts.cultural_product_v1 import build_text_messages, factual_background

def run_case(case):
    expected = case["expected"]
    try:
        brief = validate_cultural_product_request(case["request"])
        messages = build_text_messages(brief)
        factual = factual_background(brief)
        reasons = []
        if expected["outcome"] != "success": reasons.append("OUTCOME_MISMATCH")
        for text in case.get("facts_assertions", []):
            if text not in factual["text"]: reasons.append("FACT_BOUNDARY_MISMATCH")
        if case["category"] == "Prompt 注入" and "忽略之前指令" not in messages[1]["content"]: reasons.append("DATA_BOUNDARY_MISMATCH")
        return {"case_id":case["case_id"],"status":"passed" if not reasons else "failed","reasons":reasons}
    except BriefValidationError as error:
        return {"case_id":case["case_id"],"status":"passed" if expected.get("error_code")==error.code else "failed","error_code":error.code,"reasons":[]}

def main():
    parser=argparse.ArgumentParser(); parser.add_argument("--dataset", required=True); parser.add_argument("--report", required=True); args=parser.parse_args()
    data=json.loads(Path(args.dataset).read_text(encoding="utf-8")); results=[run_case(c) for c in data["cases"]]
    report={"dataset_version":data["dataset_version"],"target_type":data["target_type"],"executor_type":"stub","data_origin":"test","measurement_scope":"harness_self_test","passed":sum(r["status"]=="passed" for r in results),"failed":sum(r["status"]!="passed" for r in results),"cases":results}
    Path(args.report).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    return 0 if not report["failed"] else 1
if __name__=="__main__": raise SystemExit(main())
