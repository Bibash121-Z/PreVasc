# Generated manually to add patient phone field

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0003_patient_created_at_patientfollowup'),
    ]

    operations = [
        migrations.AddField(
            model_name='patient',
            name='phone_no',
            field=models.CharField(blank=True, max_length=20, null=True),
        ),
    ]
