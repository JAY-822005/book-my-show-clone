from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from movies.models import SEAT_RESERVATION_TIMEOUT_MINUTES, Seat


class Command(BaseCommand):
    """
    Releases any seat holds that have outlived SEAT_RESERVATION_TIMEOUT_MINUTES.

    The app already does this lazily on every relevant request (seat selection,
    checkout), so seats never stay stuck for someone who keeps visiting the
    site. This command exists as a belt-and-suspenders option for deployments
    that want a periodic cron/cleanup job too (e.g. `python manage.py
    release_expired_seats` on a schedule).
    """

    help = "Release any seat reservations that have passed the hold timeout."

    def handle(self, *args, **options):
        cutoff = timezone.now() - timedelta(minutes=SEAT_RESERVATION_TIMEOUT_MINUTES)
        qs = Seat.objects.filter(
            reserved_by__isnull=False,
            is_booked=False,
            reserved_at__lt=cutoff,
        )
        count = qs.count()
        qs.update(reserved_by=None, reserved_at=None)
        self.stdout.write(self.style.SUCCESS(f"Released {count} expired seat reservation(s)."))
