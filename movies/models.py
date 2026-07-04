from datetime import timedelta

from django.conf import settings as django_settings
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


# How long a seat stays "held" for a user before it's released back to the pool.
SEAT_RESERVATION_TIMEOUT_MINUTES = getattr(
    django_settings, 'SEAT_RESERVATION_TIMEOUT_MINUTES', 5
)


class Movie(models.Model):

    GENRE_CHOICES = [
        ('action', 'Action'),
        ('comedy', 'Comedy'),
        ('drama', 'Drama'),
        ('horror', 'Horror'),
        ('romance', 'Romance'),
        ('thriller', 'Thriller'),
        ('sci_fi', 'Sci-Fi'),
        ('animation', 'Animation'),
        ('biography', 'Biography'),
        ('documentary', 'Documentary'),
    ]

    LANGUAGE_CHOICES = [
        ('hindi', 'Hindi'),
        ('english', 'English'),
        ('tamil', 'Tamil'),
        ('telugu', 'Telugu'),
        ('kannada', 'Kannada'),
        ('malayalam', 'Malayalam'),
        ('marathi', 'Marathi'),
        ('punjabi', 'Punjabi'),
    ]

    name = models.CharField(max_length=255)
    image = models.ImageField(upload_to="movies/")
    rating = models.DecimalField(max_digits=3, decimal_places=1)
    cast = models.TextField()
    description = models.TextField(blank=True, null=True)
    genre = models.CharField(
        max_length=50,
        choices=GENRE_CHOICES,
        default='action',
    )
    language = models.CharField(
        max_length=50,
        choices=LANGUAGE_CHOICES,
        default='hindi',
    )
    trailer_url = models.URLField(
        blank=True,
        null=True,
        help_text="YouTube link, e.g. https://www.youtube.com/watch?v=XXXXXXXXXXX",
    )

    def __str__(self):
        return self.name

    def get_genre_display_label(self):
        return dict(self.GENRE_CHOICES).get(self.genre, self.genre)

    def get_language_display_label(self):
        return dict(self.LANGUAGE_CHOICES).get(self.language, self.language)

    def get_trailer_embed_url(self):
        """Normalize any YouTube URL format into an /embed/ URL usable in an <iframe>."""
        url = (self.trailer_url or '').strip()
        if not url:
            return None

        video_id = None
        if 'youtu.be/' in url:
            video_id = url.split('youtu.be/')[-1].split('?')[0]
        elif 'watch?v=' in url:
            video_id = url.split('watch?v=')[-1].split('&')[0]
        elif '/embed/' in url:
            return url
        elif '/shorts/' in url:
            video_id = url.split('/shorts/')[-1].split('?')[0]

        if video_id:
            return f'https://www.youtube.com/embed/{video_id}'
        return None


class Theater(models.Model):
    name = models.CharField(max_length=255)
    movie = models.ForeignKey(Movie, on_delete=models.CASCADE, related_name='theaters')
    time = models.DateTimeField()
    price = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=200.00,
        help_text="Ticket price per seat for this show (INR)",
    )

    def __str__(self):
        return f'{self.name} - {self.movie.name} at {self.time}'


class Seat(models.Model):
    theater = models.ForeignKey(Theater, on_delete=models.CASCADE, related_name='seats')
    seat_number = models.CharField(max_length=10)
    is_booked = models.BooleanField(default=False)

    # Temporary hold while a user is checking out / paying.
    reserved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reserved_seats',
    )
    reserved_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f'{self.seat_number} in {self.theater.name}'

    @property
    def is_reservation_expired(self):
        if self.reserved_at is None:
            return False
        deadline = self.reserved_at + timedelta(minutes=SEAT_RESERVATION_TIMEOUT_MINUTES)
        return timezone.now() > deadline

    @property
    def is_held(self):
        """True if seat is currently reserved by someone and the hold hasn't expired."""
        return bool(self.reserved_by) and not self.is_reservation_expired and not self.is_booked

    def release_if_expired(self):
        """Lazily clear a stale hold. Returns True if it released something."""
        if self.reserved_by and not self.is_booked and self.is_reservation_expired:
            self.reserved_by = None
            self.reserved_at = None
            self.save(update_fields=['reserved_by', 'reserved_at'])
            return True
        return False


class Order(models.Model):
    """One checkout attempt: a set of seats a user is paying for together."""

    STATUS_CHOICES = [
        ('created', 'Created'),
        ('paid', 'Paid'),
        ('failed', 'Failed'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='orders')
    theater = models.ForeignKey(Theater, on_delete=models.CASCADE, related_name='orders')
    seats = models.ManyToManyField(Seat, related_name='orders')
    amount = models.DecimalField(max_digits=10, decimal_places=2)

    razorpay_order_id = models.CharField(max_length=100, blank=True)
    razorpay_payment_id = models.CharField(max_length=100, blank=True)
    razorpay_signature = models.CharField(max_length=255, blank=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='created')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'Order #{self.id} - {self.user.username} - {self.get_status_display()}'

    @property
    def seat_numbers(self):
        return ', '.join(s.seat_number for s in self.seats.all().order_by('seat_number'))


class Booking(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    seat = models.OneToOneField(Seat, on_delete=models.CASCADE)
    movie = models.ForeignKey(Movie, on_delete=models.CASCADE)
    theater = models.ForeignKey(Theater, on_delete=models.CASCADE)
    order = models.ForeignKey(
        Order, on_delete=models.SET_NULL, null=True, blank=True, related_name='bookings'
    )
    booked_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'Booking by {self.user.username} for {self.seat.seat_number} at {self.theater.name}'
