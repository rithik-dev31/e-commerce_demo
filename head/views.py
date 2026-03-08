from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Count, Sum, Q
from django.utils import timezone
from django.urls import reverse_lazy
from datetime import timedelta, datetime
from django.http import JsonResponse, HttpResponse
from django.core.paginator import Paginator
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.core import serializers
import json
import csv
from public.models import Order, OrderItem, MenuItem, Category, OrderTracking
from decimal import Decimal

# Custom JSON encoder to handle Decimal objects
class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        elif isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)

@staff_member_required
@login_required(login_url=reverse_lazy("signin"))
def admin_dashboard(request):
    """Main admin dashboard with overview statistics"""
    # Get date range for filters (default: last 7 days)
    date_range = request.GET.get('range', '7')
    if date_range == '30':
        days = 30
    elif date_range == '90':
        days = 90
    else:
        days = 7
    
    start_date = timezone.now() - timedelta(days=days)
    
    # Basic statistics
    total_orders = Order.objects.count()
    pending_orders = Order.objects.filter(status=Order.PENDING).count()
    completed_orders = Order.objects.filter(status=Order.DELIVERED).count()
    cancelled_orders = Order.objects.filter(status=Order.CANCELLED).count()
    
    # Revenue calculations
    total_revenue = Order.objects.filter(
        status=Order.DELIVERED
    ).aggregate(total=Sum('total_amount'))['total'] or Decimal('0.00')
    
    recent_revenue = Order.objects.filter(
        status=Order.DELIVERED,
        created_at__gte=start_date
    ).aggregate(total=Sum('total_amount'))['total'] or Decimal('0.00')
    
    # Recent orders
    recent_orders = Order.objects.select_related('user').order_by('-created_at')[:10]
    
    # Orders by status for chart
    orders_by_status = {
        'Pending': Order.objects.filter(status=Order.PENDING).count(),
        'Confirmed': Order.objects.filter(status=Order.CONFIRMED).count(),
        'Preparing': Order.objects.filter(status=Order.PREPARING).count(),
        'Ready': Order.objects.filter(status=Order.READY).count(),
        'Out for Delivery': Order.objects.filter(status=Order.OUT_FOR_DELIVERY).count(),
        'Delivered': Order.objects.filter(status=Order.DELIVERED).count(),
        'Cancelled': Order.objects.filter(status=Order.CANCELLED).count(),
    }
    
    # Daily orders for the period
    daily_orders = []
    for i in range(days):
        day = start_date + timedelta(days=i)
        day_end = day + timedelta(days=1)
        count = Order.objects.filter(created_at__range=[day, day_end]).count()
        daily_orders.append({
            'date': day.strftime('%Y-%m-%d'),
            'count': count
        })
    
    # Top selling items
    top_items = OrderItem.objects.values(
        'menu_item__name', 'menu_item__id'
    ).annotate(
        total_quantity=Sum('quantity'),
        total_revenue=Sum('price')
    ).order_by('-total_quantity')[:10]
    
    context = {
        'total_orders': total_orders,
        'pending_orders': pending_orders,
        'completed_orders': completed_orders,
        'cancelled_orders': cancelled_orders,
        'total_revenue': total_revenue,
        'recent_revenue': recent_revenue,
        'recent_orders': recent_orders,
        'orders_by_status': orders_by_status,
        'daily_orders': daily_orders,
        'top_items': top_items,
        'date_range': date_range,
    }
    
    return render(request, 'dashboard.html', context)


@staff_member_required
@login_required(login_url=reverse_lazy("signin"))
def order_list(request):
    """List all orders with filtering and search"""
    orders = Order.objects.select_related('user').prefetch_related('order_items').all().order_by('-created_at')
    
    # Filter by status
    status_filter = request.GET.get('status', '')
    if status_filter:
        orders = orders.filter(status=status_filter)
    
    # Search by order ID, customer name, or phone
    search_query = request.GET.get('search', '')
    if search_query:
        orders = orders.filter(
            Q(id__icontains=search_query) |
            Q(user__username__icontains=search_query) |
            Q(user__email__icontains=search_query) |
            Q(phone_number__icontains=search_query)
        )
    
    # Date range filter
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    if date_from and date_to:
        orders = orders.filter(created_at__date__range=[date_from, date_to])
    elif date_from:
        orders = orders.filter(created_at__date__gte=date_from)
    elif date_to:
        orders = orders.filter(created_at__date__lte=date_to)
    
    # Pagination
    paginator = Paginator(orders, 20)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    
    context = {
        'page_obj': page_obj,
        'status_filter': status_filter,
        'search_query': search_query,
        'date_from': date_from,
        'date_to': date_to,
        'status_choices': Order.STATUS_CHOICES,
    }
    
    return render(request, 'order_list.html', context)


@staff_member_required
@login_required(login_url=reverse_lazy("signin"))
def order_detail(request, order_id):
    """View and manage individual order"""
    print(f"Fetching details for order ID: {order_id}")
    order = get_object_or_404(
        Order.objects.select_related('user').prefetch_related(
            'order_items__menu_item',
            'tracking'
        ),
        id=order_id
    )
    
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'update_status':
            new_status = request.POST.get('status')
            if new_status in dict(Order.STATUS_CHOICES):
                old_status = order.status
                order.status = new_status
                order.save()
                
                # Create tracking entry
                OrderTracking.objects.create(
                    order=order,
                    status=new_status,
                    notes=f"Status changed from {old_status} to {new_status} by admin"
                )
                
                messages.success(request, f'Order #{order.id} status updated to {new_status}')
        
        elif action == 'update_tracking':
            location = request.POST.get('location', '')
            notes = request.POST.get('notes', '')
            
            OrderTracking.objects.create(
                order=order,
                status=order.status,
                location=location,
                notes=notes
            )
            
            messages.success(request, 'Tracking information added')
        
        elif action == 'cancel_order':
            order.status = Order.CANCELLED
            order.save()
            
            OrderTracking.objects.create(
                order=order,
                status=Order.CANCELLED,
                notes="Order cancelled by admin"
            )
            
            messages.warning(request, f'Order #{order.id} has been cancelled')
        
        return redirect('head:order_detail', order_id=order.id)
    
    context = {
        'order': order,
        'status_choices': Order.STATUS_CHOICES,
        'tracking_history': order.tracking.all(),
    }
    
    return render(request, 'order_detail.html', context)


@staff_member_required
@login_required(login_url=reverse_lazy("signin"))
def bulk_order_action(request):
    """Handle bulk actions on orders"""
    if request.method == 'POST':
        action = request.POST.get('bulk_action')
        order_ids = request.POST.getlist('order_ids')
        
        if not order_ids:
            messages.warning(request, 'No orders selected')
            return redirect('head:order_list')
        
        orders = Order.objects.filter(id__in=order_ids)
        
        if action == 'mark_confirmed':
            orders.update(status=Order.CONFIRMED)
            for order in orders:
                OrderTracking.objects.create(
                    order=order,
                    status=Order.CONFIRMED,
                    notes="Bulk action: Confirmed"
                )
            messages.success(request, f'{orders.count()} orders marked as confirmed')
        
        elif action == 'mark_ready':
            orders.update(status=Order.READY)
            for order in orders:
                OrderTracking.objects.create(
                    order=order,
                    status=Order.READY,
                    notes="Bulk action: Ready for pickup/delivery"
                )
            messages.success(request, f'{orders.count()} orders marked as ready')
        
        elif action == 'mark_delivered':
            orders.update(status=Order.DELIVERED)
            for order in orders:
                OrderTracking.objects.create(
                    order=order,
                    status=Order.DELIVERED,
                    notes="Bulk action: Delivered"
                )
            messages.success(request, f'{orders.count()} orders marked as delivered')
        
        elif action == 'delete':
            # Only allow deletion of cancelled orders
            orders.filter(status=Order.CANCELLED).delete()
            messages.success(request, f'Deleted {orders.count()} cancelled orders')
        
        return redirect('head:order_list')
    
    return redirect('head:order_list')

@staff_member_required
@login_required(login_url=reverse_lazy("signin"))
def order_statistics(request):
    """Detailed order statistics and analytics"""
    # Get date range
    period = request.GET.get('period', 'month')
    
    if period == 'week':
        start_date = timezone.now() - timedelta(days=7)
    elif period == 'month':
        start_date = timezone.now() - timedelta(days=30)
    elif period == 'year':
        start_date = timezone.now() - timedelta(days=365)
    else:
        start_date = timezone.now() - timedelta(days=30)
    
    # Get all orders within date range
    orders_in_range = Order.objects.filter(created_at__gte=start_date)
    
    # Orders over time - using safe aggregation
    orders_over_time = []
    current_date = start_date.date()
    end_date = timezone.now().date()
    
    while current_date <= end_date:
        next_date = current_date + timedelta(days=1)
        day_orders = orders_in_range.filter(
            created_at__date__gte=current_date,
            created_at__date__lt=next_date
        )
        count = day_orders.count()
        revenue = day_orders.aggregate(total=Sum('total_amount'))['total'] or 0
        
        orders_over_time.append({
            'date': current_date.isoformat(),
            'count': count,
            'revenue': float(revenue)
        })
        
        current_date = next_date
    
    # Status distribution
    status_distribution = []
    for status_code, status_label in Order.STATUS_CHOICES:
        count = orders_in_range.filter(status=status_code).count()
        revenue = orders_in_range.filter(
            status=status_code
        ).aggregate(total=Sum('total_amount'))['total'] or 0
        
        if count > 0:  # Only include statuses that have orders
            status_distribution.append({
                'status': status_code,
                'label': status_label,
                'count': count,
                'revenue': float(revenue)
            })
    
    # Peak hours - using Python to extract hours
    peak_hours = []
    hour_counts = {}
    
    for order in orders_in_range:
        hour = order.created_at.hour
        hour_counts[hour] = hour_counts.get(hour, 0) + 1
    
    # Convert to list and sort by count (descending)
    for hour, count in sorted(hour_counts.items(), key=lambda x: x[1], reverse=True)[:10]:
        peak_hours.append({
            'hour': hour,
            'count': count
        })
    
    # Sort by hour for display
    peak_hours.sort(key=lambda x: x['hour'])
    
    # Average order value
    delivered_orders = orders_in_range.filter(status=Order.DELIVERED)
    delivered_count = delivered_orders.count()
    if delivered_count > 0:
        total_revenue = delivered_orders.aggregate(total=Sum('total_amount'))['total'] or 0
        avg_order_value = float(total_revenue) / delivered_count
    else:
        avg_order_value = 0
    
    # Customer statistics
    top_customers = Order.objects.filter(
        status=Order.DELIVERED
    ).values(
        'user__username', 'user__email'
    ).annotate(
        order_count=Count('id'),
        total_spent=Sum('total_amount')
    ).order_by('-total_spent')[:10]
    
    # Convert to list for template
    top_customers_list = list(top_customers)
    for customer in top_customers_list:
        if customer.get('total_spent'):
            customer['total_spent'] = float(customer['total_spent'])
    
    # Overall statistics
    total_orders = Order.objects.count()
    total_revenue = Order.objects.filter(
        status=Order.DELIVERED
    ).aggregate(total=Sum('total_amount'))['total'] or 0
    
    context = {
        'period': period,
        'orders_over_time': orders_over_time,
        'status_distribution': status_distribution,
        'peak_hours': peak_hours,
        'avg_order_value': round(avg_order_value, 2),
        'top_customers': top_customers_list,
        'total_orders': total_orders,
        'total_revenue': float(total_revenue),
    }
    
    return render(request, 'order_statistics.html', context)

@staff_member_required
def export_orders(request):
    """Export orders data as CSV"""
    # Get orders based on filters
    orders = Order.objects.select_related('user').prefetch_related('order_items').all()
    
    # Apply filters if any
    status = request.GET.get('status')
    if status:
        orders = orders.filter(status=status)
    
    date_from = request.GET.get('date_from')
    if date_from:
        orders = orders.filter(created_at__date__gte=date_from)
    
    date_to = request.GET.get('date_to')
    if date_to:
        orders = orders.filter(created_at__date__lte=date_to)
    
    # Create CSV response
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="orders_export_{timezone.now().strftime("%Y%m%d_%H%M%S")}.csv"'
    
    writer = csv.writer(response)
    writer.writerow(['Order ID', 'Customer', 'Email', 'Phone', 'Total Amount', 'Status', 'Items', 'Order Date', 'Delivery Address'])
    
    for order in orders:
        items = ', '.join([f"{item.quantity}x {item.menu_item.name}" for item in order.order_items.all() if item.menu_item])
        writer.writerow([
            order.id,
            order.user.get_full_name() or order.user.username,
            order.user.email,
            order.phone_number,
            order.total_amount,
            order.get_status_display(),
            items,
            order.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            order.delivery_address
        ])
    
    return response


# API endpoints for AJAX requests (Orders)
@staff_member_required
def get_order_status_counts(request):
    """API endpoint to get real-time order counts"""
    counts = {
        'pending': Order.objects.filter(status=Order.PENDING).count(),
        'confirmed': Order.objects.filter(status=Order.CONFIRMED).count(),
        'preparing': Order.objects.filter(status=Order.PREPARING).count(),
        'ready': Order.objects.filter(status=Order.READY).count(),
        'out_for_delivery': Order.objects.filter(status=Order.OUT_FOR_DELIVERY).count(),
        'delivered': Order.objects.filter(status=Order.DELIVERED).count(),
        'cancelled': Order.objects.filter(status=Order.CANCELLED).count(),
    }
    return JsonResponse(counts)


@staff_member_required
def update_order_status_ajax(request, order_id):
    """AJAX endpoint to update order status"""
    if request.method == 'POST':
        order = get_object_or_404(Order, id=order_id)
        new_status = request.POST.get('status')
        
        if new_status in dict(Order.STATUS_CHOICES):
            old_status = order.status
            order.status = new_status
            order.save()
            
            OrderTracking.objects.create(
                order=order,
                status=new_status,
                notes=f"Status changed from {old_status} to {new_status} by admin"
            )
            
            return JsonResponse({
                'success': True,
                'message': f'Order #{order.id} status updated',
                'new_status': new_status,
                'new_status_display': dict(Order.STATUS_CHOICES)[new_status]
            })
        
        return JsonResponse({'success': False, 'message': 'Invalid status'}, status=400)
    
    return JsonResponse({'success': False, 'message': 'Method not allowed'}, status=405)


# ==================== CATEGORY MANAGEMENT (AJAX-based) ====================

@staff_member_required
@login_required(login_url=reverse_lazy("signin"))
def category_management(request):
    """Main category management page (renders template)"""
    return render(request, 'category_management.html')
    

@staff_member_required
def category_list_api(request):
    """API endpoint to get all categories"""
    categories = Category.objects.annotate(
        item_count=Count('items')
    ).values('id', 'name', 'slug', 'item_count', 'created_at')
    
    # Convert to list and handle date serialization
    categories_list = list(categories)
    for cat in categories_list:
        if 'created_at' in cat and cat['created_at']:
            cat['created_at'] = cat['created_at'].isoformat()
    
    return JsonResponse({
        'success': True,
        'categories': categories_list
    }, encoder=DecimalEncoder)


@staff_member_required
@require_http_methods(["POST"])
def category_create_api(request):
    """API endpoint to create a new category"""
    try:
        data = json.loads(request.body)
        name = data.get('name')
        slug = data.get('slug')
        
        if not name or not slug:
            return JsonResponse({
                'success': False,
                'error': 'Name and slug are required'
            }, status=400)
        
        # Check if slug is unique
        if Category.objects.filter(slug=slug).exists():
            return JsonResponse({
                'success': False,
                'error': 'Slug already exists'
            }, status=400)
        
        category = Category.objects.create(
            name=name,
            slug=slug
        )
        
        return JsonResponse({
            'success': True,
            'message': f'Category "{name}" created successfully',
            'category': {
                'id': category.id,
                'name': category.name,
                'slug': category.slug,
                'created_at': category.created_at.isoformat()
            }
        }, encoder=DecimalEncoder)
        
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON data'
        }, status=400)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@staff_member_required
def category_detail_api(request, category_id):
    """API endpoint to get category details"""
    try:
        category = Category.objects.annotate(
            item_count=Count('items')
        ).get(id=category_id)
        
        # Get menu items in this category
        menu_items = category.items.all().values(
            'id', 'name', 'price', 'available', 'rating', 'reviews_count'
        )
        
        return JsonResponse({
            'success': True,
            'category': {
                'id': category.id,
                'name': category.name,
                'slug': category.slug,
                'item_count': category.item_count,
                'created_at': category.created_at.isoformat(),
                'menu_items': list(menu_items)
            }
        }, encoder=DecimalEncoder)
        
    except Category.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Category not found'
        }, status=404)


@staff_member_required
@require_http_methods(["POST"])
def category_update_api(request, category_id):
    """API endpoint to update a category"""
    try:
        category = Category.objects.get(id=category_id)
        data = json.loads(request.body)
        
        name = data.get('name')
        slug = data.get('slug')
        
        if not name or not slug:
            return JsonResponse({
                'success': False,
                'error': 'Name and slug are required'
            }, status=400)
        
        # Check if slug is unique (excluding current category)
        if Category.objects.filter(slug=slug).exclude(id=category_id).exists():
            return JsonResponse({
                'success': False,
                'error': 'Slug already exists'
            }, status=400)
        
        category.name = name
        category.slug = slug
        category.save()
        
        return JsonResponse({
            'success': True,
            'message': f'Category updated successfully',
            'category': {
                'id': category.id,
                'name': category.name,
                'slug': category.slug
            }
        })
        
    except Category.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Category not found'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@staff_member_required
@require_http_methods(["POST"])
def category_delete_api(request, category_id):
    """API endpoint to delete a category"""
    try:
        category = Category.objects.get(id=category_id)
        
        # Check if category has items
        item_count = category.items.count()
        if item_count > 0:
            return JsonResponse({
                'success': False,
                'error': f'Cannot delete category with {item_count} menu items. Move or delete them first.'
            }, status=400)
        
        category_name = category.name
        category.delete()
        
        return JsonResponse({
            'success': True,
            'message': f'Category "{category_name}" deleted successfully'
        })
        
    except Category.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Category not found'
        }, status=404)


# ==================== MENU ITEM MANAGEMENT (AJAX-based) ====================

@staff_member_required
def menu_item_management(request):
    """Main menu item management page (renders template)"""
    categories = Category.objects.all()
    return render(request, 'menuitem_management.html', {'categories': categories})


@staff_member_required
def menu_item_list_api(request):
    """API endpoint to get all menu items with filters"""
    items = MenuItem.objects.select_related('category').all()
    
    # Apply filters
    category_id = request.GET.get('category')
    if category_id:
        items = items.filter(category_id=category_id)
    
    availability = request.GET.get('availability')
    if availability == 'available':
        items = items.filter(available=True)
    elif availability == 'unavailable':
        items = items.filter(available=False)
    
    search = request.GET.get('search')
    if search:
        items = items.filter(
            Q(name__icontains=search) |
            Q(description__icontains=search)
        )
    
    # Pagination
    page = int(request.GET.get('page', 1))
    page_size = 20
    start = (page - 1) * page_size
    end = start + page_size
    
    total_count = items.count()
    items = items.order_by('category__name', 'name')[start:end]
    
    items_list = []
    for item in items:
        items_list.append({
            'id': item.id,
            'name': item.name,
            'description': item.description[:100] + '...' if len(item.description) > 100 else item.description,
            'price': float(item.price),
            'category': {
                'id': item.category.id,
                'name': item.category.name
            },
            'image_url': item.image_url,
            'rating': float(item.rating),
            'reviews_count': item.reviews_count,
            'available': item.available,
            'created_at': item.created_at.isoformat()
        })
    
    return JsonResponse({
        'success': True,
        'items': items_list,
        'total_count': total_count,
        'current_page': page,
        'total_pages': (total_count + page_size - 1) // page_size
    })


@staff_member_required
@require_http_methods(["POST"])
def menu_item_create_api(request):
    """API endpoint to create a new menu item"""
    try:
        data = json.loads(request.body)
        
        name = data.get('name')
        description = data.get('description')
        price = data.get('price')
        category_id = data.get('category_id')
        image_url = data.get('image_url', '')
        rating = data.get('rating', 4.5)
        available = data.get('available', True)
        
        if not all([name, description, price, category_id]):
            return JsonResponse({
                'success': False,
                'error': 'Name, description, price, and category are required'
            }, status=400)
        
        try:
            category = Category.objects.get(id=category_id)
        except Category.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'Invalid category'
            }, status=400)
        
        menu_item = MenuItem.objects.create(
            name=name,
            description=description,
            price=price,
            category=category,
            image_url=image_url,
            rating=rating,
            available=available
        )
        
        return JsonResponse({
            'success': True,
            'message': f'Menu item "{name}" created successfully',
            'item': {
                'id': menu_item.id,
                'name': menu_item.name,
                'price': float(menu_item.price),
                'category': {
                    'id': category.id,
                    'name': category.name
                },
                'available': menu_item.available
            }
        }, encoder=DecimalEncoder)
        
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON data'
        }, status=400)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@staff_member_required
def menu_item_detail_api(request, item_id):
    """API endpoint to get menu item details"""
    try:
        menu_item = MenuItem.objects.select_related('category').get(id=item_id)
        
        # Get order statistics for this item
        order_stats = OrderItem.objects.filter(
            menu_item=menu_item
        ).aggregate(
            total_orders=Count('order'),
            total_quantity=Sum('quantity'),
            total_revenue=Sum('price')
        )
        
        return JsonResponse({
            'success': True,
            'item': {
                'id': menu_item.id,
                'name': menu_item.name,
                'description': menu_item.description,
                'price': float(menu_item.price),
                'category': {
                    'id': menu_item.category.id,
                    'name': menu_item.category.name
                },
                'image_url': menu_item.image_url,
                'rating': float(menu_item.rating),
                'reviews_count': menu_item.reviews_count,
                'available': menu_item.available,
                'created_at': menu_item.created_at.isoformat(),
                'updated_at': menu_item.updated_at.isoformat(),
                'order_stats': {
                    'total_orders': order_stats['total_orders'] or 0,
                    'total_quantity': order_stats['total_quantity'] or 0,
                    'total_revenue': float(order_stats['total_revenue'] or 0)
                }
            }
        }, encoder=DecimalEncoder)
        
    except MenuItem.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Menu item not found'
        }, status=404)


@staff_member_required
@require_http_methods(["POST"])
def menu_item_update_api(request, item_id):
    """API endpoint to update a menu item"""
    try:
        menu_item = MenuItem.objects.get(id=item_id)
        data = json.loads(request.body)
        
        name = data.get('name')
        description = data.get('description')
        price = data.get('price')
        category_id = data.get('category_id')
        image_url = data.get('image_url', '')
        rating = data.get('rating', menu_item.rating)
        available = data.get('available', menu_item.available)
        
        if not all([name, description, price, category_id]):
            return JsonResponse({
                'success': False,
                'error': 'Name, description, price, and category are required'
            }, status=400)
        
        try:
            category = Category.objects.get(id=category_id)
        except Category.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'Invalid category'
            }, status=400)
        
        menu_item.name = name
        menu_item.description = description
        menu_item.price = price
        menu_item.category = category
        menu_item.image_url = image_url
        menu_item.rating = rating
        menu_item.available = available
        menu_item.save()
        
        return JsonResponse({
            'success': True,
            'message': f'Menu item "{name}" updated successfully',
            'item': {
                'id': menu_item.id,
                'name': menu_item.name,
                'price': float(menu_item.price),
                'category': {
                    'id': category.id,
                    'name': category.name
                },
                'available': menu_item.available
            }
        }, encoder=DecimalEncoder)
        
    except MenuItem.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Menu item not found'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@staff_member_required
@require_http_methods(["POST"])
def menu_item_delete_api(request, item_id):
    """API endpoint to delete a menu item"""
    try:
        menu_item = MenuItem.objects.get(id=item_id)
        
        # Check if item has been ordered
        order_count = OrderItem.objects.filter(menu_item=menu_item).count()
        if order_count > 0:
            return JsonResponse({
                'success': False,
                'warning': True,
                'message': f'This item has been ordered {order_count} times. Consider marking it as unavailable instead.',
                'order_count': order_count
            }, status=400)
        
        item_name = menu_item.name
        menu_item.delete()
        
        return JsonResponse({
            'success': True,
            'message': f'Menu item "{item_name}" deleted successfully'
        })
        
    except MenuItem.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Menu item not found'
        }, status=404)


@staff_member_required
@require_http_methods(["POST"])
def toggle_item_availability_api(request, item_id):
    """API endpoint to toggle menu item availability"""
    try:
        menu_item = MenuItem.objects.get(id=item_id)
        menu_item.available = not menu_item.available
        menu_item.save()
        
        status = "available" if menu_item.available else "unavailable"
        
        return JsonResponse({
            'success': True,
            'message': f'Menu item "{menu_item.name}" is now {status}',
            'available': menu_item.available
        })
        
    except MenuItem.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Menu item not found'
        }, status=404)
    



@staff_member_required
def order_list_api(request):
    """API endpoint to get orders with filtering"""
    orders = Order.objects.select_related('user').order_by('-created_at')[:10]
    
    orders_list = []
    for order in orders:
        orders_list.append({
            'id': order.id,
            'user__username': order.user.username,
            'total_amount': float(order.total_amount),
            'status': order.status,
            'status_display': order.get_status_display(),
            'created_at': order.created_at.isoformat()
        })
    
    return JsonResponse({
        'success': True,
        'orders': orders_list
    })