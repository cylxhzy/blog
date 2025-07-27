from prometheus_client import start_http_server, Counter, Gauge
import logging
import time

logger = logging.getLogger(__name__)

# 定义监控指标
VIEW_REQUESTS = Counter('view_requests_total', '文章访问请求总数')
SYNC_TASKS = Counter('sync_tasks_total', '同步任务执行总数')
SYNC_SUCCESS = Counter('sync_success_total', '同步成功次数')
SYNC_FAILURE = Counter('sync_failure_total', '同步失败次数')
REDIS_QUEUE_SIZE = Gauge('redis_queue_size', 'Redis队列大小')


def start_metrics_server(port=9100):
    """启动Prometheus指标服务器"""
    start_http_server(port)
    logger.info(f"Metrics server started on port {port}")


def record_sync_result(success=True):
    """记录同步任务结果"""
    if success:
        SYNC_SUCCESS.inc()
    else:
        SYNC_FAILURE.inc()


def update_queue_size(size):
    """更新队列大小指标"""
    REDIS_QUEUE_SIZE.set(size)
