from django.urls import path
from . import views

app_name = 'head'

urlpatterns = [
    # Dashboard
    path('dashboard/', views.admin_dashboard, name='admin_dashboard'),
    
    # Order Management
    path('orders/', views.order_list, name='order_list'),
    path('orders/<int:order_id>/', views.order_detail, name='order_detail'),
    path('orders/bulk-action/', views.bulk_order_action, name='bulk_order_action'),
    path('orders/statistics/', views.order_statistics, name='order_statistics'),
    path('orders/export/', views.export_orders, name='export_orders'),
    path('api/orders/recent/', views.order_list_api, name='order_list_api'),

    # Category Management - Main view and AJAX endpoints
    path('categories/', views.category_management, name='category_management'),
    path('api/categories/', views.category_list_api, name='category_list_api'),
    path('api/categories/create/', views.category_create_api, name='category_create_api'),
    path('api/categories/<int:category_id>/', views.category_detail_api, name='category_detail_api'),
    path('api/categories/<int:category_id>/update/', views.category_update_api, name='category_update_api'),
    path('api/categories/<int:category_id>/delete/', views.category_delete_api, name='category_delete_api'),
    
    # Menu Item Management - Main view and AJAX endpoints
    path('menu-items/', views.menu_item_management, name='menu_item_management'),
    path('api/menu-items/', views.menu_item_list_api, name='menu_item_list_api'),
    path('api/menu-items/create/', views.menu_item_create_api, name='menu_item_create_api'),
    path('api/menu-items/<int:item_id>/', views.menu_item_detail_api, name='menu_item_detail_api'),
    path('api/menu-items/<int:item_id>/update/', views.menu_item_update_api, name='menu_item_update_api'),
    path('api/menu-items/<int:item_id>/delete/', views.menu_item_delete_api, name='menu_item_delete_api'),
    path('api/menu-items/<int:item_id>/toggle-availability/', views.toggle_item_availability_api, name='toggle_item_availability_api'),
    
    # API Endpoints for orders
    path('api/order-status-counts/', views.get_order_status_counts, name='order_status_counts'),
    path('api/orders/<int:order_id>/update-status/', views.update_order_status_ajax, name='update_order_status_ajax'),
]