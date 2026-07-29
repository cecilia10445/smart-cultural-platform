"""Operations dashboard and evaluation-report endpoints."""

from fastapi import APIRouter, Request

from backend.routes._bridge import invoke

router = APIRouter(tags=["dashboard"])


def _api():
    from backend.routes import api
    return api


@router.get("/api/dashboard/quality-report")
async def quality_report(request: Request):
    return await invoke(_api().get_quality_report, request)

@router.get("/api/dashboard/quality-report/html")
async def quality_report_html(request: Request): return await invoke(_api().download_quality_report_html, request)

@router.get("/api/dashboard/quality-reports")
async def quality_reports(request: Request): return await invoke(_api().list_round17c_quality_reports, request)

@router.get("/api/dashboard/quality-reports/{run_id}")
async def quality_report_run(run_id: str, request: Request): return await invoke(_api().get_round17c_quality_report, request, run_id=run_id)

@router.get("/api/dashboard/business-generation-reports")
async def business_reports(request: Request): return await invoke(_api().list_round17c_business_reports, request)

@router.get("/api/dashboard/business-generation-reports/{run_id}")
async def business_report_run(run_id: str, request: Request): return await invoke(_api().get_round17c_business_report, request, run_id=run_id)

@router.get("/api/dashboard/stats")
async def stats(request: Request): return await invoke(_api().get_dashboard_stats, request)

@router.get("/api/dashboard/user-profile")
async def user_profile(request: Request): return await invoke(_api().get_user_profile_dashboard, request)

@router.get("/api/recommendations/personalized")
async def recommendations(request: Request): return await invoke(_api().get_personalized_recommendations, request)
