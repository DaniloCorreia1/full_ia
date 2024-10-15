from django.contrib import admin
from django.urls import include, path
from django.shortcuts import redirect 

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('ai_app.urls')),  # Inclua as URLs do ai_app

    
]
