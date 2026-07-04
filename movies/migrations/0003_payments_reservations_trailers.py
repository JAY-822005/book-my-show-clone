import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('movies', '0002_movie_genre_movie_language'),
    ]

    operations = [
        migrations.AddField(
            model_name='movie',
            name='trailer_url',
            field=models.URLField(
                blank=True,
                null=True,
                help_text="YouTube link, e.g. https://www.youtube.com/watch?v=XXXXXXXXXXX",
            ),
        ),
        migrations.AddField(
            model_name='theater',
            name='price',
            field=models.DecimalField(
                decimal_places=2,
                default=200.00,
                max_digits=8,
                help_text="Ticket price per seat for this show (INR)",
            ),
        ),
        migrations.AddField(
            model_name='seat',
            name='reserved_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='seat',
            name='reserved_by',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='reserved_seats',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.CreateModel(
            name='Order',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('amount', models.DecimalField(decimal_places=2, max_digits=10)),
                ('razorpay_order_id', models.CharField(blank=True, max_length=100)),
                ('razorpay_payment_id', models.CharField(blank=True, max_length=100)),
                ('razorpay_signature', models.CharField(blank=True, max_length=255)),
                ('status', models.CharField(
                    choices=[('created', 'Created'), ('paid', 'Paid'), ('failed', 'Failed')],
                    default='created',
                    max_length=20,
                )),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('seats', models.ManyToManyField(related_name='orders', to='movies.seat')),
                ('theater', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='orders', to='movies.theater')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='orders', to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.AddField(
            model_name='booking',
            name='order',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='bookings',
                to='movies.order',
            ),
        ),
    ]
