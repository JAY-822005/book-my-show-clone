from django.urls import path
from . import views

urlpatterns = [
    path('', views.movie_list, name='movie_list'),
    path('<int:movie_id>/theaters', views.theater_list, name='theater_list'),

    # Booking / payment flow
    path('theater/<int:theater_id>/seats/book/', views.book_seats, name='book_seats'),
    path('checkout/<int:order_id>/', views.checkout, name='checkout'),
    path('payment/callback/', views.payment_callback, name='payment_callback'),
    path('payment/success/<int:order_id>/', views.payment_success, name='payment_success'),
    path('payment/failed/<int:order_id>/', views.payment_failed, name='payment_failed'),

    # Admin analytics
    path('dashboard/', views.admin_dashboard, name='admin_dashboard'),
]
