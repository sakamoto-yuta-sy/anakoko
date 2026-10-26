from django.urls import path
from poker import views
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.contrib.auth.views import LogoutView

urlpatterns = [
    path("", views.game_list, name="game_list"),
    path("create/", views.game_create, name="game_create"),
    path("<int:game_id>/", views.game_detail, name="game_detail"),
    path("<int:game_id>/order/", views.add_order, name="add_order"),
    path("<int:game_id>/rebuy/", views.add_rebuy, name="add_rebuy"),
    path("<int:game_id>/settlement/", views.settlement_view, name="settlement"),
    path("<int:game_id>/ranking/", views.chip_ranking, name="chip_ranking"),
    path("<int:game_id>/edit/", views.game_edit, name="game_edit"),

    path("<int:game_id>/result/", views.add_result, name="add_result"),
    path("admin/", admin.site.urls),
    path("users/create/", views.user_create, name="user_create"),
    path("users/password/reset/", views.user_password_reset, name="user_password_reset"),

    path(
        "login/",
        auth_views.LoginView.as_view(template_name="login.html"),
        name="login",
    ),
    path("logout/", LogoutView.as_view(next_page="login"), name="logout"),
    path(
        "password/change/",
        auth_views.PasswordChangeView.as_view(template_name="password_change.html"),
        name="password_change",
    ),
    path(
        "password/change/done/",
        auth_views.PasswordChangeDoneView.as_view(template_name="password_change_done.html"),
        name="password_change_done",
    ),
]
