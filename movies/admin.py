from django.contrib import admin
from .models import Booking, Movie, Order, Seat, Theater


@admin.register(Movie)
class MovieAdmin(admin.ModelAdmin):
    list_display = ['name', 'genre', 'language', 'rating', 'cast', 'description', 'trailer_url']
    list_filter = ['genre', 'language', 'rating']
    search_fields = ['name', 'cast', 'description']


@admin.register(Theater)
class TheaterAdmin(admin.ModelAdmin):
    list_display = ['name', 'movie', 'time', 'price']
    list_filter = ['movie']


@admin.register(Seat)
class SeatAdmin(admin.ModelAdmin):
    list_display = ['theater', 'seat_number', 'is_booked', 'reserved_by', 'reserved_at']
    list_filter = ['is_booked', 'theater']


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'theater', 'amount', 'status', 'created_at']
    list_filter = ['status', 'created_at']
    search_fields = ['user__username', 'razorpay_order_id', 'razorpay_payment_id']
    readonly_fields = ['razorpay_order_id', 'razorpay_payment_id', 'razorpay_signature']


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ['user', 'seat', 'movie', 'theater', 'order', 'booked_at']
    list_filter = ['theater', 'movie']
