import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags

logger = logging.getLogger(__name__)


def send_booking_confirmation_email(order, bookings):
    """
    Sends an HTML (+ plaintext fallback) email confirming a successful booking.

    Uses fail_silently so a flaky email backend never breaks the booking flow
    itself -- the booking/payment has already succeeded by the time this runs.
    """
    user = order.user
    if not user.email:
        logger.warning("Booking #%s: user %s has no email on file, skipping confirmation email.",
                        order.id, user.username)
        return False

    context = {
        'order': order,
        'bookings': bookings,
        'user': user,
        'movie': order.theater.movie,
        'theater': order.theater,
        'seat_numbers': order.seat_numbers,
    }

    subject = f"Your tickets for {order.theater.movie.name} are confirmed 🎬"
    html_body = render_to_string('movies/email/booking_confirmation.html', context)
    text_body = strip_tags(html_body)

    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'BookMySeat <no-reply@bookmyseat.com>')

    email = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email=from_email,
        to=[user.email],
    )
    email.attach_alternative(html_body, 'text/html')

    try:
        email.send(fail_silently=False)
        return True
    except Exception:
        logger.exception("Failed to send booking confirmation email for order #%s", order.id)
        return False
