from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('movies', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='movie',
            name='genre',
            field=models.CharField(
                choices=[
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
                ],
                default='action',
                max_length=50,
            ),
        ),
        migrations.AddField(
            model_name='movie',
            name='language',
            field=models.CharField(
                choices=[
                    ('hindi', 'Hindi'),
                    ('english', 'English'),
                    ('tamil', 'Tamil'),
                    ('telugu', 'Telugu'),
                    ('kannada', 'Kannada'),
                    ('malayalam', 'Malayalam'),
                    ('marathi', 'Marathi'),
                    ('punjabi', 'Punjabi'),
                ],
                default='hindi',
                max_length=50,
            ),
        ),
    ]
