# FastAPI migration progress

## Baseline route inventory

| Domain | Method | Path | Legacy handler |
| --- | --- | --- | --- |
| static | GET | `/` | `home` |
| static | GET | `/{filename:path}` | `serve_static` |
| auth | POST | `/api/login` | `login` |
| auth | POST | `/api/register` | `register` |
| generation | POST | `/api/generate` | `generate_content_api` |
| generation | POST | `/api/v2/cultural-products/generate` | `generate_cultural_product_api` |
| generation | POST | `/api/v2/cultural-products/generate-with-text-skill` | `generate_cultural_product_with_text_skill_api` |
| generation | GET | `/api/v2/cultural-products/text-skill-generations/{run_id}` | `get_cultural_product_text_skill_generation_api` |
| dashboard | GET | `/api/dashboard/quality-report` | `get_quality_report` |
| dashboard | GET | `/api/dashboard/quality-report/html` | `download_quality_report_html` |
| dashboard | GET | `/api/dashboard/quality-reports` | `list_round17c_quality_reports` |
| dashboard | GET | `/api/dashboard/quality-reports/{run_id}` | `get_round17c_quality_report` |
| dashboard | GET | `/api/dashboard/business-generation-reports` | `list_round17c_business_reports` |
| dashboard | GET | `/api/dashboard/business-generation-reports/{run_id}` | `get_round17c_business_report` |
| dashboard | GET | `/api/dashboard/stats` | `get_dashboard_stats` |
| users | GET | `/api/user/profile` | `get_user_profile` |
| users | GET | `/api/user/history` | `get_user_history` |
| users | POST | `/api/rating` | `submit_rating` |
| users | POST | `/api/download` | `record_download` |
| media | GET | `/static/images/{filename}` | `serve_static_images` |
| dashboard | GET | `/api/dashboard/user-profile` | `get_user_profile_dashboard` |
| dashboard | GET | `/api/recommendations/personalized` | `get_personalized_recommendations` |
| system | GET | `/api/health`, `/api/health/live` | `health_check` |
| system | GET | `/api/health/ready` | `readiness_check` |

## Progress

- System liveness: native `backend.routes.health` completed.
- Media image delivery: native `backend.routes.media` completed.
- Authentication: native `/api/login` and `/api/register` endpoints registered by `routes.auth`.
- Users: all four public user endpoints registered by `routes.users`.
- Dashboard: reports, stats, user profile, and recommendations registered by `routes.dashboard`.
- Generation: legacy and v2 generation endpoints registered by `routes.generation`.
- Static frontend: registered by `routes.frontend` after API routers so it cannot shadow API paths.
- The remaining legacy implementation module supplies transitional handler bodies only; its decorator no longer registers routes.

## Verification

- `python -m compileall -q backend`: passed after the domain-router switch.
- `backend.app:create_app`: imports successfully and enumerates 26 application methods/routes.
- Primary URL/method comparison: all checked health, auth, user, dashboard, generation, and media routes are present (`missing []`).
- Focused endpoint calls: liveness returned `{"status": "alive"}`; media rejected traversal with 404; invalid login returned 400; unauthenticated user, dashboard, and generation calls each returned 401.
- The full-ASGI request command (`timeout 20 ... httpx.ASGITransport(app=create_app())`) reached `GET /api/health` but did not complete before timeout. Direct endpoint calls above work; this remains an integration-test blocker and is not treated as a passing end-to-end check.
- Known test blocker: the pre-existing aggregate compatibility router can block ASGI integration requests; per-domain tests use independently mounted routers until extraction completes.
