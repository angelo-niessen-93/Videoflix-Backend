from django.urls import path

from . import views

urlpatterns = [
    path("csrf/", views.CsrfView.as_view(), name="csrf"),
    path("register/", views.RegisterView.as_view(), name="register"),
    path(
        "activate/<str:uidb64>/<str:token>/",
        views.ActivateView.as_view(),
        name="activate",
    ),
    path("login/", views.LoginView.as_view(), name="login"),
    path("logout/", views.LogoutView.as_view(), name="logout"),
    path("token/refresh/", views.RefreshView.as_view(), name="refresh"),
    path("password_reset/", views.PasswordResetView.as_view(), name="reset"),
    path(
        "password_confirm/<str:uidb64>/<str:token>/",
        views.PasswordConfirmView.as_view(),
        name="confirm",
    ),
]
