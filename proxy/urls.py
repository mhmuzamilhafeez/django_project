from django.urls import path, re_path
from proxy import views

urlpatterns = [
    path('health/', views.proxy_health, name='proxy.health'),
    path('test-connection/', views.proxy_test_connection, name='proxy.test'),
    re_path(r'^(?P<path>.*)$', views.proxy_forward, name='proxy.forward'),
]
