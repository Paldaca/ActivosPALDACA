"""Log request performance metrics in development."""

import logging
from time import perf_counter

from django.conf import settings
from django.db import connection

logger = logging.getLogger("paldaca.performance")


class DevelopmentPerformanceMiddleware:
    """Measure total time, SQL time, query count, and response size."""

    def __init__(self, get_response):
        self.get_response = get_response
        self.enabled = settings.DEBUG

    def __call__(self, request):
        if not self.enabled:
            return self.get_response(request)

        query_start = len(connection.queries)
        started_at = perf_counter()
        response = self.get_response(request)
        elapsed_ms = (perf_counter() - started_at) * 1000

        queries = connection.queries[query_start:]
        sql_ms = sum(
            float(query.get("time", 0) or 0) * 1000
            for query in queries
        )
        response_size = self._response_size(response)
        response["Server-Timing"] = (
            f'app;dur={elapsed_ms:.1f}, '
            f'db;dur={sql_ms:.1f};desc="{len(queries)} queries"'
        )
        logger.info(
            "PERF_REQUEST path=%r method=%r status=%s total_ms=%.1f "
            "sql_ms=%.1f queries=%s response_bytes=%s",
            request.path,
            request.method,
            response.status_code,
            elapsed_ms,
            sql_ms,
            len(queries),
            response_size,
        )
        return response

    @staticmethod
    def _response_size(response):
        if getattr(response, "streaming", False):
            return None
        return len(response.content)
