from django.urls import path 
from .views import *


urlpatterns = [ 
    path('',index, name='home'), 
    path('signup/',signup_page , name='signup'),
    path('signin/',signin_page,name='signin'),
    path('admin_page/',admin_page,name='admin_page'),
    # path('dashboard/', dashboard, name='dashboard'),  # Assuming you have a dashboard view
]
