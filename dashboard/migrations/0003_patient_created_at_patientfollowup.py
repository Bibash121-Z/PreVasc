# Generated manually for patient follow-up reporting support

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0002_patient_heart_rate'),
    ]

    operations = [
        migrations.AddField(
            model_name='patient',
            name='created_at',
            field=models.DateTimeField(auto_now_add=True, blank=True, null=True),
        ),
        migrations.CreateModel(
            name='PatientFollowUp',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('heart_rate', models.FloatField(blank=True, null=True)),
                ('si', models.FloatField(blank=True, null=True)),
                ('cvd_risk', models.CharField(blank=True, max_length=64, null=True)),
                ('cvd_age', models.FloatField(blank=True, null=True)),
                ('pwv', models.FloatField(blank=True, null=True)),
                ('ct', models.FloatField(blank=True, null=True)),
                ('ri', models.FloatField(blank=True, null=True)),
                ('dpdt_max', models.FloatField(blank=True, null=True)),
                ('agi_mod', models.FloatField(blank=True, null=True)),
                ('lvet', models.FloatField(blank=True, null=True)),
                ('ppg_sevr', models.FloatField(blank=True, null=True)),
                ('ppg_asys', models.FloatField(blank=True, null=True)),
                ('ppg_adia', models.FloatField(blank=True, null=True)),
                ('pat', models.FloatField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('patient', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='followups', to='dashboard.patient')),
            ],
        ),
    ]
