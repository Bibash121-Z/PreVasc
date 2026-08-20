# models.py
from django.db import models

class Patient(models.Model):
    # This automatically increments from 1 upwards with each save (e.g., 1, 2, 3...)
    id = models.AutoField(primary_key=True) 
    name = models.CharField(max_length=255)
    phone_no = models.CharField(max_length=20, null=True, blank=True)
    age = models.IntegerField()
    gender = models.CharField(max_length=50)
    height = models.FloatField()
    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)

    # --- ADD THIS SINGLE NEW FIELD HERE ---
    heart_rate = models.FloatField(null=True, blank=True)

    def __str__(self):
        return f"Patient {self.id}: {self.name}"


class PatientFollowUp(models.Model):
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='followups')
    heart_rate = models.FloatField(null=True, blank=True)
    
    # --- NEW EXPLICIT BLOOD PRESSURE FIELDS ---
    sbp = models.FloatField(null=True, blank=True)
    dbp = models.FloatField(null=True, blank=True)

    si = models.FloatField(null=True, blank=True)
    cvd_risk = models.CharField(max_length=64, null=True, blank=True)
    cvd_age = models.FloatField(null=True, blank=True)
    pwv = models.FloatField(null=True, blank=True)
    ct = models.FloatField(null=True, blank=True)
    ri = models.FloatField(null=True, blank=True)
    dpdt_max = models.FloatField(null=True, blank=True)
    agi_mod = models.FloatField(null=True, blank=True)
    lvet = models.FloatField(null=True, blank=True)
    ppg_sevr = models.FloatField(null=True, blank=True)
    ppg_asys = models.FloatField(null=True, blank=True)
    ppg_adia = models.FloatField(null=True, blank=True)
    pat = models.FloatField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"FollowUp PT-{self.patient_id} @ {self.created_at}"