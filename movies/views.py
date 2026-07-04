import json
import logging

from django.conf import settings
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError
from django.db.models import Count, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .emails import send_booking_confirmation_email
from .models import Booking, Movie, Order, Seat, Theater

logger = logging.getLogger(__name__)

try:
    import razorpay
except ImportError:  # pragma: no cover - guarded so the app still boots without the package
    razorpay = None


# ──────────────────────────────────────────────────────────────────────────
# Movie browsing
# ──────────────────────────────────────────────────────────────────────────

def movie_list(request):
    movies = Movie.objects.all()

    search_query = request.GET.get('search', '').strip()
    selected_genre = request.GET.get('genre', '').strip()
    selected_language = request.GET.get('language', '').strip()

    if search_query:
        movies = movies.filter(name__icontains=search_query)

    if selected_genre:
        movies = movies.filter(genre=selected_genre)

    if selected_language:
        movies = movies.filter(language=selected_language)

    context = {
        'movies': movies,
        'genre_choices': Movie.GENRE_CHOICES,
        'language_choices': Movie.LANGUAGE_CHOICES,
        'selected_genre': selected_genre,
        'selected_language': selected_language,
        'search_query': search_query,
    }
    return render(request, 'movies/movie_list.html', context)


def theater_list(request, movie_id):
    movie = get_object_or_404(Movie, id=movie_id)
    theaters = Theater.objects.filter(movie=movie).order_by('time')
    return render(request, 'movies/theater_list.html', {'movie': movie, 'theaters': theaters})


# ──────────────────────────────────────────────────────────────────────────
# Seat reservation (with timeout) + checkout
# ──────────────────────────────────────────────────────────────────────────

def _release_expired_reservations(theater=None):
    """Lazily clear out any seat holds that have timed out.

    Called at the top of any view that reads seat availability, so stale
    holds never block other users -- no background worker required.
    """
    from datetime import timedelta
    from .models import SEAT_RESERVATION_TIMEOUT_MINUTES

    qs = Seat.objects.filter(reserved_by__isnull=False, is_booked=False)
    if theater is not None:
        qs = qs.filter(theater=theater)

    cutoff = timezone.now() - timedelta(minutes=SEAT_RESERVATION_TIMEOUT_MINUTES)
    qs.filter(reserved_at__lt=cutoff).update(reserved_by=None, reserved_at=None)


@login_required(login_url='/login/')
def book_seats(request, theater_id):
    """
    Step 1 of checkout: shows the seat map. On POST, places a temporary hold
    on the chosen seats (released automatically after SEAT_RESERVATION_TIMEOUT_MINUTES
    if payment isn't completed) and creates an Order, then sends the user to checkout.
    """
    from .models import SEAT_RESERVATION_TIMEOUT_MINUTES

    theaters = get_object_or_404(Theater, id=theater_id)
    _release_expired_reservations(theater=theaters)
    seats = Seat.objects.filter(theater=theaters).order_by('seat_number')

    if request.method == 'POST':
        selected_seat_ids = request.POST.getlist('seats')

        if not selected_seat_ids:
            return render(request, "movies/seat_selection.html", {
                'theaters': theaters,
                "seats": seats,
                'error': "No seat selected",
                'reservation_minutes': SEAT_RESERVATION_TIMEOUT_MINUTES,
            })

        unavailable = []
        seats_to_reserve = []
        for seat_id in selected_seat_ids:
            seat = get_object_or_404(Seat, id=seat_id, theater=theaters)
            seat.release_if_expired()
            if seat.is_booked or (seat.reserved_by_id and seat.reserved_by_id != request.user.id):
                unavailable.append(seat.seat_number)
            else:
                seats_to_reserve.append(seat)

        if unavailable:
            error_message = f"These seats were just taken by someone else: {', '.join(unavailable)}. Please choose again."
            return render(request, 'movies/seat_selection.html', {
                'theaters': theaters,
                "seats": seats,
                'error': error_message,
                'reservation_minutes': SEAT_RESERVATION_TIMEOUT_MINUTES,
            })

        now = timezone.now()
        for seat in seats_to_reserve:
            seat.reserved_by = request.user
            seat.reserved_at = now
            seat.save(update_fields=['reserved_by', 'reserved_at'])

        amount = theaters.price * len(seats_to_reserve)

        order = Order.objects.create(
            user=request.user,
            theater=theaters,
            amount=amount,
            status='created',
        )
        order.seats.set(seats_to_reserve)

        gateway_configured = bool(settings.RAZORPAY_KEY_ID and settings.RAZORPAY_KEY_SECRET and razorpay)

        if gateway_configured:
            try:
                client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
                razorpay_order = client.order.create({
                    'amount': int(amount * 100),  # Razorpay expects paise
                    'currency': 'INR',
                    'receipt': f'order_rcptid_{order.id}',
                    'payment_capture': 1,
                })
                order.razorpay_order_id = razorpay_order['id']
                order.save(update_fields=['razorpay_order_id'])
            except Exception:
                logger.exception("Razorpay order creation failed for internal order #%s", order.id)
                order.razorpay_order_id = f'demo_order_{order.id}'
                order.save(update_fields=['razorpay_order_id'])
        else:
            # No gateway keys configured (e.g. local/demo run) -- fall back to a
            # simulated order id so the rest of the flow (UI, timeout, email) is
            # still fully testable end-to-end.
            order.razorpay_order_id = f'demo_order_{order.id}'
            order.save(update_fields=['razorpay_order_id'])

        return redirect('checkout', order_id=order.id)

    return render(request, 'movies/seat_selection.html', {
        'theaters': theaters,
        "seats": seats,
        'reservation_minutes': SEAT_RESERVATION_TIMEOUT_MINUTES,
    })


@login_required(login_url='/login/')
def checkout(request, order_id):
    """Step 2: payment page. Shows a live countdown until the seat hold expires."""
    order = get_object_or_404(Order, id=order_id, user=request.user)

    if order.status != 'created':
        return redirect('payment_success' if order.status == 'paid' else 'payment_failed', order_id=order.id)

    order_seats = list(order.seats.all())
    for seat in order_seats:
        seat.release_if_expired()

    expired = any(
        (seat.reserved_by_id != request.user.id) or seat.is_booked
        for seat in order_seats
    )
    if expired:
        order.status = 'failed'
        order.save(update_fields=['status'])
        messages.warning(request, "Your seat hold expired before payment was completed. Please select seats again.")
        return redirect('theater_list', movie_id=order.theater.movie.id)

    from datetime import timedelta
    from .models import SEAT_RESERVATION_TIMEOUT_MINUTES
    earliest_hold = min((s.reserved_at for s in order_seats if s.reserved_at), default=timezone.now())
    deadline = earliest_hold + timedelta(minutes=SEAT_RESERVATION_TIMEOUT_MINUTES)
    seconds_left = max(int((deadline - timezone.now()).total_seconds()), 0)

    gateway_configured = bool(settings.RAZORPAY_KEY_ID and settings.RAZORPAY_KEY_SECRET and razorpay)

    context = {
        'order': order,
        'seats': order_seats,
        'razorpay_key': settings.RAZORPAY_KEY_ID,
        'seconds_left': seconds_left,
        'gateway_configured': gateway_configured,
        'amount_paise': int(order.amount * 100),
    }
    return render(request, 'movies/checkout.html', context)


@login_required
@require_POST
def payment_callback(request):
    """
    Handles both real Razorpay callbacks (signature verified server-side) and
    the demo-mode fallback used when no gateway keys are configured.
    """
    order_id = request.POST.get('order_id')
    order = get_object_or_404(Order, id=order_id, user=request.user)

    if order.status == 'paid':
        return redirect('payment_success', order_id=order.id)

    razorpay_payment_id = request.POST.get('razorpay_payment_id', '')
    razorpay_order_id = request.POST.get('razorpay_order_id', '')
    razorpay_signature = request.POST.get('razorpay_signature', '')

    gateway_configured = bool(settings.RAZORPAY_KEY_ID and settings.RAZORPAY_KEY_SECRET and razorpay)

    verified = False
    if gateway_configured and razorpay_payment_id and razorpay_signature:
        client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
        try:
            client.utility.verify_payment_signature({
                'razorpay_order_id': razorpay_order_id,
                'razorpay_payment_id': razorpay_payment_id,
                'razorpay_signature': razorpay_signature,
            })
            verified = True
        except razorpay.errors.SignatureVerificationError:
            verified = False
    elif not gateway_configured:
        # Demo mode: no real gateway to verify against, auto-approve so the
        # success/failure/email flow can still be exercised end-to-end.
        verified = True

    # Re-check seats weren't released by the timeout while the user was paying.
    order_seats = list(order.seats.all())
    still_valid = all(
        (not s.is_booked) and s.reserved_by_id == request.user.id and not s.is_reservation_expired
        for s in order_seats
    )

    if not verified or not still_valid:
        order.status = 'failed'
        order.razorpay_payment_id = razorpay_payment_id
        order.save(update_fields=['status', 'razorpay_payment_id'])
        return redirect('payment_failed', order_id=order.id)

    order.razorpay_payment_id = razorpay_payment_id or f'demo_payment_{order.id}'
    order.razorpay_signature = razorpay_signature
    order.status = 'paid'
    order.save()

    bookings = []
    for seat in order_seats:
        seat.is_booked = True
        seat.reserved_by = None
        seat.reserved_at = None
        seat.save(update_fields=['is_booked', 'reserved_by', 'reserved_at'])
        try:
            booking = Booking.objects.create(
                user=request.user,
                seat=seat,
                movie=order.theater.movie,
                theater=order.theater,
                order=order,
            )
            bookings.append(booking)
        except IntegrityError:
            logger.error("Seat %s already had a Booking row while finalizing order #%s", seat.id, order.id)

    send_booking_confirmation_email(order, bookings)

    return redirect('payment_success', order_id=order.id)


@login_required
def payment_success(request, order_id):
    order = get_object_or_404(Order, id=order_id, user=request.user, status='paid')
    bookings = order.bookings.select_related('seat', 'theater', 'movie')
    return render(request, 'movies/payment_success.html', {'order': order, 'bookings': bookings})


@login_required
def payment_failed(request, order_id):
    order = get_object_or_404(Order, id=order_id, user=request.user)
    return render(request, 'movies/payment_failed.html', {'order': order})


# ──────────────────────────────────────────────────────────────────────────
# Admin analytics dashboard
# ──────────────────────────────────────────────────────────────────────────

@staff_member_required
def admin_dashboard(request):
    paid_orders = Order.objects.filter(status='paid')

    total_revenue = paid_orders.aggregate(total=Sum('amount'))['total'] or 0
    total_orders = paid_orders.count()
    total_bookings = Booking.objects.count()
    total_movies = Movie.objects.count()

    popular_movies = (
        Booking.objects.values('movie__name')
        .annotate(ticket_count=Count('id'))
        .order_by('-ticket_count')[:5]
    )

    busiest_theaters = (
        Booking.objects.values('theater__name')
        .annotate(booking_count=Count('id'))
        .order_by('-booking_count')[:5]
    )

    revenue_by_movie = (
        paid_orders.values('theater__movie__name')
        .annotate(revenue=Sum('amount'))
        .order_by('-revenue')[:5]
    )

    recent_orders = (
        paid_orders.select_related('user', 'theater', 'theater__movie')
        .order_by('-created_at')[:10]
    )

    context = {
        'total_revenue': total_revenue,
        'total_orders': total_orders,
        'total_bookings': total_bookings,
        'total_movies': total_movies,
        'popular_movies': popular_movies,
        'busiest_theaters': busiest_theaters,
        'revenue_by_movie': revenue_by_movie,
        'recent_orders': recent_orders,
        'popular_movies_labels': json.dumps([m['movie__name'] for m in popular_movies]),
        'popular_movies_data': json.dumps([m['ticket_count'] for m in popular_movies]),
        'theater_labels': json.dumps([t['theater__name'] for t in busiest_theaters]),
        'theater_data': json.dumps([t['booking_count'] for t in busiest_theaters]),
        'revenue_labels': json.dumps([r['theater__movie__name'] for r in revenue_by_movie]),
        'revenue_data': json.dumps([float(r['revenue']) for r in revenue_by_movie]),
    }
    return render(request, 'movies/admin_dashboard.html', context)
