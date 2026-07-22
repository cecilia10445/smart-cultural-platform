"""Short-lived, content-free persistence for v2 generation observability."""

from __future__ import annotations

import hashlib
import time
from datetime import datetime

from backend.domain.cultural_product_brief import canonical_brief_json


class TrackingPersistenceError(RuntimeError):
    pass


class GenerationTracker:
    def __init__(self, mysql_service, request_id, user_id, data_origin, brief, template_version):
        self.mysql_service = mysql_service
        self.request_id = request_id
        self.started_at = time.perf_counter()
        self._started = False
        self._attempt = (user_id, data_origin, "cultural_product", template_version, self.brief_sha256(brief))

    @staticmethod
    def brief_sha256(brief):
        return hashlib.sha256(canonical_brief_json(brief).encode("utf-8")).hexdigest()

    @staticmethod
    def _milliseconds(started):
        return max(0, round((time.perf_counter() - started) * 1000))

    def start(self):
        query = """INSERT INTO generation_attempts
            (request_id,user_id,data_origin,generation_kind,prompt_template_version,brief_sha256,status)
            VALUES (%s,%s,%s,%s,%s,%s,'RUNNING')"""
        if self.mysql_service.execute_insert(query, (self.request_id, *self._attempt)) is None:
            raise TrackingPersistenceError("TRACKING_INIT_FAILED")
        self._started = True

    def record_metric(self, stage, model_name, status, started, error=None, usage=None, image_count=None):
        usage = usage or {}
        query = """INSERT INTO model_call_metrics
            (request_id,stage,model_name,status,latency_ms,provider_http_status,provider_error_code,
             input_tokens,output_tokens,total_tokens,image_count)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"""
        values = (
            self.request_id, stage, model_name or "unknown", status, self._milliseconds(started),
            getattr(error, "http_status", None), getattr(error, "provider_error_code", None),
            usage.get("input_tokens"), usage.get("output_tokens"), usage.get("total_tokens"), image_count,
        )
        if self.mysql_service.execute_insert(query, values) is None:
            raise TrackingPersistenceError("TRACKING_METRIC_PERSIST_FAILED")

    def succeed(self, generation_log_id):
        self._finish("SUCCEEDED", generation_log_id=generation_log_id)

    def fail(self, stage, error_code):
        self._finish("FAILED", failed_stage=stage, error_code=error_code)

    def _finish(self, status, generation_log_id=None, failed_stage=None, error_code=None):
        if not self._started:
            return
        query = """UPDATE generation_attempts
            SET status=%s, failed_stage=%s, error_code=%s, generation_log_id=%s,
                total_latency_ms=%s, finished_at=%s WHERE request_id=%s AND status='RUNNING'"""
        result = self.mysql_service.execute_query(query, (
            status, failed_stage, error_code, generation_log_id, self._milliseconds(self.started_at),
            datetime.now(), self.request_id,
        ), max_retries=0)
        if result != 1:
            raise TrackingPersistenceError("TRACKING_FINALIZE_FAILED")
