from django.contrib import admin
from django.urls import include, path, re_path
from django.views.generic import TemplateView
from rest_framework.routers import DefaultRouter

from accounts import views as account_views
from expenses import views as expense_views
from imports import views as import_views

router = DefaultRouter()
router.register("groups", expense_views.GroupViewSet, basename="group")

group_router = DefaultRouter()
group_router.register("members", expense_views.GroupMemberViewSet, basename="member")
group_router.register("expenses", expense_views.ExpenseViewSet, basename="expense")
group_router.register("settlements", expense_views.SettlementViewSet, basename="settlement")

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/auth/register/", account_views.register),
    path("api/auth/login/", account_views.LoginView.as_view()),
    path("api/auth/me/", account_views.me),
    path("api/", include(router.urls)),
    path("api/groups/<int:group_pk>/", include(group_router.urls)),
    path("api/groups/<int:group_id>/imports/", import_views.batch_list),
    path("api/groups/<int:group_id>/imports/<int:batch_id>/", import_views.batch_detail),
    path(
        "api/groups/<int:group_id>/imports/<int:batch_id>/anomalies/<int:anomaly_id>/resolve/",
        import_views.resolve_anomaly,
    ),
    path(
        "api/groups/<int:group_id>/imports/<int:batch_id>/approve-all/",
        import_views.approve_all,
    ),
    path(
        "api/groups/<int:group_id>/imports/<int:batch_id>/redetect/",
        import_views.redetect,
    ),
    path("api/groups/<int:group_id>/imports/<int:batch_id>/commit/", import_views.commit),
    path("api/groups/<int:group_id>/imports/<int:batch_id>/report/", import_views.report),
    # SPA fallback: client-side routes (e.g. /groups/3) get index.html;
    # whitenoise serves the hashed asset files at the root.
    re_path(
        r"^(?!api/|admin/|assets/|static/).*$",
        TemplateView.as_view(template_name="index.html"),
    ),
]
