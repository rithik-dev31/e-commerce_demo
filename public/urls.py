from django.urls import path
from .views import *

urlpatterns = [
    path('dashboard/', public_dashboard, name='public_dashboard'),
    path('menu/', menu, name='menu'),
    path('checkout/',checkout, name='checkout'),
    path('order/<int:order_id>/confirmation/', order_confirmation, name='order_confirmation'),
    path('orders/', order_list, name='order_list'),
    path('api/order/<int:order_id>/status/', order_status_api, name='order_status_api'),
    path('logout/', user_logout, name='logout'),
]