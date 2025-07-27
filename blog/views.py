from django.shortcuts import get_object_or_404, render
from django.views import View
from django.http import JsonResponse
from .models import Article
from .views_utils import ViewCounter
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
import logging

logger = logging.getLogger(__name__)


class ArticleDetailView(View):
    @method_decorator(never_cache)
    def get(self, request, pk):
        article = get_object_or_404(Article, pk=pk)
        user = request.user

        # 记录阅读行为
        view_counter = ViewCounter()
        view_counter.record_view(article, user)

        # 获取阅读统计
        stats = view_counter.get_article_stats(article)

        context = {
            'article': article,
            'stats': stats
        }
        return render(request, 'blog/article_detail.html', context)


class ArticleStatsAPI(View):
    def get(self, request, pk):
        article = get_object_or_404(Article, pk=pk)
        view_counter = ViewCounter()
        stats = view_counter.get_article_stats(article)
        return JsonResponse(stats)


class StatsDashboard(View):
    def get(self, request):
        view_counter = ViewCounter()
        redis = view_counter.redis

        context = {
            'cache_hit_rate': view_counter.get_cache_hit_rate(),
            'queue_size': redis.get_queue_length(),
        }
        return render(request, 'blog/stats_dashboard.html', context)