from django.shortcuts import render

# Create your views here.
from django.http import HttpResponse 

from django.shortcuts import render, redirect
from django.urls import reverse

def index(request):
    # Debug prints (optional)
    print("Authenticated:", request.user.is_authenticated)
    print("Has public_user_profile:", hasattr(request.user, "profile"))

    # If user is not logged in, show signup page
    if not request.user.is_authenticated:
        return redirect("signin")

    # If user has a public_user_profile → redirect to public user page
    if hasattr(request.user, "profile"):
        return redirect(reverse("public_dashboard"))
        # return redirect("dashboard")

    # Otherwise → this is an admin, go to admin home
    return redirect(reverse("head:admin_dashboard"))
    
    


from django.shortcuts import render
from django.contrib.auth.models import User
from django.contrib.auth import login
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.db.models import Q
from .models import Public_user 


@csrf_exempt
def signup_page(request):
    if request.method == "POST":
        # Frontend already validated everything - just check duplicates & create
        first_name = request.POST.get("fname")
        last_name = request.POST.get("lname")
        username = request.POST.get("username")
        email = request.POST.get("email")
        phone = request.POST.get("phone")
        address = request.POST.get("address")
        city = request.POST.get("city")
        pincode = request.POST.get("pincode")
        password = request.POST.get("password")

        # ONLY check duplicates (frontend handles all other validation)
        if User.objects.filter(Q(username=username) | Q(email=email)).exists():
            return JsonResponse({
                "status": "error",
                "message": "Username or email already exists!"
            })

        # Create user (frontend verified passwords match)
        user = User.objects.create_user(
            username=username,
            email=email,
            first_name=first_name,
            last_name=last_name,
            password=password
        )

        # Create profile (your custom model)
        Public_user.objects.create(
            user=user,
            phone=phone,
            address=address,
            city=city,
            pincode=pincode
        )

        # Auto-login
        login(request, user)

        return JsonResponse({
            "status": "success",
            "message": "Account created successfully!",
            "redirect_url": "/User/public_dashboard/"  # Your dashboard page
        })

    # Render signup page
    return render(request, "signup.html")


from django.contrib.auth import authenticate, login
from django.http import JsonResponse
from django.shortcuts import render

@csrf_exempt 
def signin_page(request):
    if request.method == "POST":
        # Accept either username or email
        identifier = request.POST.get("identifier", "").strip()
        password   = request.POST.get("password", "").strip()

        if not identifier or not password:
            return JsonResponse({
                "status": "error",
                "message": "Please fill in all fields."
            })

        # Try username first, then email lookup
        username = identifier
        if "@" in identifier:
            try:
                from django.contrib.auth.models import User
                user_obj = User.objects.get(email=identifier)
                username = user_obj.username
            except User.DoesNotExist:
                return JsonResponse({
                    "status": "error",
                    "field": "identifier",
                    "message": "No account found with that email address."
                })

        user = authenticate(request, username=username, password=password)

        if user is None:
            return JsonResponse({
                "status": "error",
                "field": "password",
                "message": "Incorrect password. Please try again."
            })

        if not user.is_active:
            return JsonResponse({
                "status": "error",
                "message": "Your account has been deactivated."
            })

        login(request, user)
        return JsonResponse({
            "status": "success",
            "message": f"Welcome back, {user.first_name or user.username}!",
            "redirect_url":"/Biriyani_Bliss_Admin/dashboard/" if user.is_superuser else  "/User/dashboard/"
        })

    if hasattr(request.user, "profile"):
        return redirect(reverse("public_dashboard"))
        # return redirect("dashboard")
    elif request.user.is_authenticated:
        if request.user.is_superuser:
            return redirect(reverse("dashboard"))
    else:
        return render(request, "signin.html")



def admin_page(request):
    return HttpResponse("Admin Page")

def dashboard(request):
    return HttpResponse("Dashboard Page")


