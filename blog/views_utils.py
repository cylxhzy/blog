import time
import os

from .models import ArticleViewStats, UserArticleView
from .redis_utils import RedisManager
from django.db import transaction
import logging
from prometheus_client import Counter, Gauge

logger = logging.getLogger(__name__)

# 监控指标
CACHE_HITS = Counter('view_cache_hits', '缓存命中次数')
CACHE_MISSES = Counter('view_cache_misses', '缓存未命中次数')
SYNC_ERRORS = Counter('view_sync_errors', '同步错误次数')


class ViewCounter:
    def __init__(self):
        self.redis = RedisManager()
        self.last_source = None

    def record_view(self, article, user):
        """记录阅读行为"""
        user_id = str(user.id) if user.is_authenticated else 'anonymous'

        # 尝试使用Redis记录
        if self.redis.record_view(article.id, user_id):
            return True

        # Redis失败时降级到数据库
        logger.warning("Redis不可用，降级到数据库直写")
        try:
            with transaction.atomic():
                # 更新总阅读量
                stats, created = ArticleViewStats.objects.get_or_create(
                    article=article,
                    defaults={'total_views': 1}
                )
                if not created:
                    stats.total_views += 1
                    stats.save()

                # 更新用户阅读记录
                if user.is_authenticated:
                    user_view, created = UserArticleView.objects.get_or_create(
                        user=user,
                        article=article,
                        defaults={'view_count': 1}
                    )
                    if not created:
                        user_view.view_count += 1
                        user_view.save()
            return True
        except Exception as e:
            logger.error(f"数据库直写失败: {str(e)}")
            return False

    def get_article_stats(self, article):
        """获取文章阅读统计"""
        # 优先从Redis获取
        redis_stats = self.redis.get_article_stats(article.id)

        if redis_stats is not None:
            self.last_source = 'redis'
            CACHE_HITS.inc()
            return redis_stats

        # Redis不可用时从数据库获取
        self.last_source = 'database'
        CACHE_MISSES.inc()
        logger.warning("Redis不可用，从数据库获取阅读统计")

        try:
            stats = ArticleViewStats.objects.get(article=article)
            user_views = UserArticleView.objects.filter(article=article)

            user_views_dict = {
                str(view.user.id): view.view_count
                for view in user_views
            }

            return {
                'total_views': stats.total_views,
                'unique_views': user_views.count(),
                'user_views': user_views_dict
            }
        except ArticleViewStats.DoesNotExist:
            return {
                'total_views': 0,
                'unique_views': 0,
                'user_views': {}
            }

    def get_cache_hit_rate(self):
        """获取缓存命中率"""
        hits = CACHE_HITS._value.get()
        misses = CACHE_MISSES._value.get()
        total = hits + misses
        return hits / total * 100 if total > 0 else 100

    def record_view(self, article, user):
        """记录阅读行为（带WAL日志）"""
        user_id = str(user.id) if user.is_authenticated else 'anonymous'

        # 写本地WAL日志
        self._write_wal_log(article.id, user_id)

        # 正常记录到Redis
        if self.redis.record_view(article.id, user_id):
            return True

        # Redis失败时尝试从WAL恢复
        self._recover_from_wal()
        return False

    def _write_wal_log(self, article_id, user_id):
        """写入预写日志"""
        try:
            with open('/var/log/view_wal.log', 'a') as f:
                f.write(f"{time.time()},{article_id},{user_id}\n")
        except Exception as e:
            logger.error(f"WAL日志写入失败: {str(e)}")

    def _recover_from_wal(self):
        """从WAL日志恢复数据"""
        try:
            if not os.path.exists('/var/log/view_wal.log'):
                return

            # 读取并处理日志
            with open('/var/log/view_wal.log', 'r') as f:
                logs = f.readlines()

            # 处理日志（简化示例）
            for log in logs[-1000:]:  # 只处理最近的1000条
                timestamp, article_id, user_id = log.strip().split(',')
                self.redis.record_view(article_id, user_id)

            # 清空日志
            open('/var/log/view_wal.log', 'w').close()
        except Exception as e:
            logger.error(f"WAL日志恢复失败: {str(e)}")
