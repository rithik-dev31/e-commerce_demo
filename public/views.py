from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST, require_GET
from django.contrib import messages
from django.db import transaction
from decimal import Decimal, InvalidOperation
import json
from django.contrib.auth import logout
from django.urls import reverse, reverse_lazy
from .models import Category, MenuItem, Order, OrderItem, OrderTracking


# ─────────────────────────────────────────────
#  PUBLIC PAGES
# ─────────────────────────────────────────────

@login_required(login_url=reverse_lazy("signin"))
def public_dashboard(request):
    """Home / landing page."""
    return render(request, "home.html")

@login_required(login_url=reverse_lazy("signin"))
def menu(request):
    """
    Full menu page.
    Categories + items rendered server-side.
    Cart is managed entirely in frontend (localStorage).
    """
    categories = Category.objects.prefetch_related(
        'items'
    ).filter(items__available=True).distinct()

    return render(request, "menu.html", {'categories': categories})


# ─────────────────────────────────────────────
#  CHECKOUT
#  GET  → render checkout.html (cart comes from localStorage via JS)
#  POST → receive cart JSON from frontend, create Order in DB
# ─────────────────────────────────────────────
@login_required
def checkout(request):

    if request.method == 'GET':
        return render(request, 'checkout.html')

    try:
        body = json.loads(request.body)
        delivery_address = body.get('delivery_address', '').strip()
        phone_number     = body.get('phone_number', '').strip()
        order_notes      = body.get('order_notes', '').strip()
        cart             = body.get('cart', [])
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({'error': 'Invalid request body.'}, status=400)

    if not delivery_address or not phone_number:
        return JsonResponse({'error': 'Delivery address and phone number are required.'}, status=400)

    if not cart:
        return JsonResponse({'error': 'Your cart is empty.'}, status=400)

    # ── Process cart data from frontend ──
    order_items_data = []
    total_amount = Decimal('0.00')

    for entry in cart:
        try:
            menu_item_id = int(entry.get('id'))
            item_name = entry.get('name', 'Unknown Item')
            item_price = Decimal(str(entry.get('price', '0')))
            quantity = int(entry.get('quantity', 1))
        except (TypeError, ValueError, InvalidOperation):
            return JsonResponse({'error': 'Invalid cart item data.'}, status=400)

        if quantity <= 0:
            continue

        item_total = item_price * quantity
        total_amount += item_total

        order_items_data.append({
            'item_id': menu_item_id,
            'item_name': item_name,
            'quantity': quantity,
            'price': item_price,
        })

    if not order_items_data:
        return JsonResponse({'error': 'No valid items in cart.'}, status=400)

    # ── Save to DB ──
    with transaction.atomic():
        order = Order.objects.create(
            user=request.user,
            total_amount=total_amount,
            delivery_address=delivery_address,
            phone_number=phone_number,
            order_notes=order_notes,
            status=Order.PENDING,
        )

        for item_data in order_items_data:
            # Set menu_item to NULL explicitly
            OrderItem.objects.create(
                order=order,
                menu_item=None,  # Explicitly set to NULL
                quantity=item_data['quantity'],
                price=item_data['price'],
            )

        OrderTracking.objects.create(
            order=order,
            status=Order.PENDING,
            notes='Order placed successfully.',
        )

    return JsonResponse({
        'success': True,
        'message': f'Order #{order.id} placed successfully!',
        'order_id': order.id,
        'redirect_url': f'/User/order/{order.id}/confirmation/',
    })
# ─────────────────────────────────────────────
#  ORDER PAGES
# ─────────────────────────────────────────────

@login_required(login_url=reverse_lazy("signin"))
def order_confirmation(request, order_id):
    """GET /order/<id>/confirmation/"""
    order = get_object_or_404(Order, id=order_id, user=request.user)
    order_items = order.order_items.select_related('menu_item').all()
    tracking = order.tracking.all()

    return render(request, 'order_confirmation.html', {
        'order': order,
        'order_items': order_items,
        'tracking': tracking,
    })


@login_required(login_url=reverse_lazy("signin"))
def order_list(request):
    """GET /orders/  — user's order history."""
    orders = request.user.orders.prefetch_related('order_items__menu_item').order_by('-created_at')
    return render(request, 'orders.html', {'orders': orders})


# ─────────────────────────────────────────────
#  ORDER STATUS API  (live polling)
# ─────────────────────────────────────────────

@login_required
@require_GET
def order_status_api(request, order_id):
    """GET /api/order/<id>/status/"""
    order = get_object_or_404(Order, id=order_id, user=request.user)
    tracking = order.tracking.values('status', 'location', 'timestamp', 'notes')

    return JsonResponse({
        'order_id': order.id,
        'status': order.status,
        'status_display': order.get_status_display(),
        'total_amount': float(order.total_amount),
        'tracking': list(tracking),
    })

def user_logout(request):
    logout(request)
    return redirect(reverse("home"))