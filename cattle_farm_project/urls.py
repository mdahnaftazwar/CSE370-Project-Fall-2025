"""
URL configuration for cattle_farm_project project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.urls import path
from farm_management.views import animal_tracking, assign_staff, login_view, logout_view ,add_breeding, breeding_log

urlpatterns = [
    path("login/", login_view, name="login"),
    path("logout/", logout_view, name="logout"),
    path("", animal_tracking, name="animal_tracking"),  # Home points to tracking
    path("assign/", assign_staff, name="assign_staff"),

    #----- Feature 3: Breeding -----> ZR
    path("breeding/<str:cattle_id>/", breeding_log, name = "breeding_log"),
    path("breeding/add/<str:cattle_id>/", add_breeding, name = "add_breeding"),
    path("calendar/", task_calendar, name="task_calendar"),
]
