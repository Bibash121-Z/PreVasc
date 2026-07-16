# models.py
from django.db import models

class Patient(models.Model):
    # This automatically increments from 1 upwards with each save (e.g., 1, 2, 3...)
    id = models.AutoField(primary_key=True) 
    name = models.CharField(max_length=255)
    age = models.IntegerField()
    gender = models.CharField(max_length=50)
    height = models.FloatField()

    def __str__(self):
        return f"Patient {self.id}: {self.name}"