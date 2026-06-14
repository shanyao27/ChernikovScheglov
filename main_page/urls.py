from . import views
from django.urls import path
from main_page.views import get_positions_by_department
from main_page import views as main_views

app_name = 'main_page'

urlpatterns = [
    path('', views.main_page, name='main_page'),
    path('login/', views.login, name='login'),
    path('registration/', views.registration, name='registration'),
    path('about/', views.about, name='about'),
    path('get-positions/', main_views.get_positions_by_department, name='get_positions'),
]
