import redis
from django.conf import settings
import json
import logging

logger = logging.getLogger(__name__)


class RedisManager:
    def __init__(self):
        self.pool = redis.ConnectionPool(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            db=settings.REDIS_DB,
            decode_responses=True
        )
        self.conn = redis.Redis(connection_pool=self.pool)

    def record_view(self, article_id, user_id):
        """记录阅读行为到Redis"""
        try:
            # 使用管道保证原子操作
            pipe = self.conn.pipeline()

            # 总阅读量增加
            pipe.hincrby(f"article:{article_id}:stats", "total_views", 1)

            # 用户阅读计数
            pipe.hincrby(f"article:{article_id}:users", user_id, 1)

            # 独立用户统计
            pipe.pfadd(f"article:{article_id}:unique_users", user_id)

            # 加入更新队列
            pipe.lpush("article:update_queue", article_id)

            # 设置过期时间
            pipe.expire(f"article:{article_id}:stats", 86400)  # 24小时
            pipe.expire(f"article:{article_id}:users", 86400)
            pipe.expire(f"article:{article_id}:unique_users", 86400)

            # 执行所有命令
            pipe.execute()
            return True
        except redis.RedisError as e:
            logger.error(f"Redis记录失败: {str(e)}")
            return False

    def get_article_stats(self, article_id):
        """获取文章阅读统计"""
        try:
            # 使用管道获取多个值
            pipe = self.conn.pipeline()
            pipe.hgetall(f"article:{article_id}:stats")
            pipe.hgetall(f"article:{article_id}:users")
            pipe.pfcount(f"article:{article_id}:unique_users")
            results = pipe.execute()

            stats = {
                'total_views': int(results[0].get('total_views', 0)) if results[0] else 0,
                'user_views': {k: int(v) for k, v in results[1].items()} if results[1] else {},
                'unique_views': results[2] or 0
            }
            return stats
        except redis.RedisError as e:
            logger.error(f"Redis查询失败: {str(e)}")
            return None

    def get_queue_length(self):
        """获取更新队列长度"""
        try:
            return self.conn.llen("article:update_queue")
        except redis.RedisError:
            return 0

    def pop_articles_from_queue(self, count=100):
        """从队列中获取待更新文章ID"""
        try:
            pipe = self.conn.pipeline()
            for _ in range(count):
                pipe.rpop("article:update_queue")
            return [id for id in pipe.execute() if id]
        except redis.RedisError:
            return []