from celery import shared_task
from .models import ArticleViewStats, UserArticleView
from .redis_utils import RedisManager
from django.db import transaction
from django.utils import timezone
from datetime import timedelta
import logging

logger = logging.getLogger(__name__)


@shared_task
def sync_views_to_db():
    """将Redis中的阅读数据同步到数据库"""
    redis = RedisManager()

    # 一次处理100个文章ID
    article_ids = redis.pop_articles_from_queue(100)
    if not article_ids:
        return

    # 去重处理
    unique_article_ids = set(article_ids)

    for article_id in unique_article_ids:
        try:
            stats = redis.get_article_stats(article_id)
            if not stats:
                continue

            with transaction.atomic():
                # 更新文章总览表
                article_view, created = ArticleViewStats.objects.update_or_create(
                    article_id=article_id,
                    defaults={'total_views': stats['total_views']}
                )

                # 更新用户阅读记录
                for user_id, count in stats['user_views'].items():
                    # 跳过匿名用户
                    if user_id == 'anonymous':
                        continue

                    UserArticleView.objects.update_or_create(
                        user_id=user_id,
                        article_id=article_id,
                        defaults={'view_count': count}
                    )

            logger.info(f"成功同步文章 {article_id} 的阅读数据")
        except Exception as e:
            logger.error(f"同步文章 {article_id} 失败: {str(e)}")



@shared_task
def validate_data_consistency():
    """验证Redis和数据库数据一致性"""
    from .models import ArticleViewStats
    from .redis_utils import RedisManager

    redis = RedisManager()

    # 获取最近更新的文章
    recent_articles = ArticleViewStats.objects.filter(
        last_updated__gte=timezone.now() - timedelta(hours=1)
    ).values_list('article_id', flat=True)

    for article_id in recent_articles:
        try:
            # 获取Redis数据
            redis_stats = redis.get_article_stats(article_id)

            # 获取数据库数据
            db_stats = ArticleViewStats.objects.get(article_id=article_id)

            # 比较总阅读量
            if redis_stats['total_views'] != db_stats.total_views:
                logger.warning(
                    f"数据不一致: 文章 {article_id} "
                    f"Redis={redis_stats['total_views']} "
                    f"DB={db_stats.total_views}"
                )

                # 自动修复 - 取较大值
                corrected_value = max(redis_stats['total_views'], db_stats.total_views)
                ArticleViewStats.objects.filter(article_id=article_id).update(
                    total_views=corrected_value
                )

                logger.info(f"已修复文章 {article_id} 的总阅读量: {corrected_value}")
        except Exception as e:
            logger.error(f"数据校验失败: {str(e)}")