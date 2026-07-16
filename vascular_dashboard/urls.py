from django.contrib import admin
from django.urls import path
# Import ALL your custom functions from your local dashboard views file
from dashboard.views import home_dashboard, get_next_patient_id, save_patient
from dashboard.views import home_dashboard, get_next_patient_id, save_patient, search_patient_api, delete_patient_api
# --- Combined Master URL Map ---
# All web paths must live inside this SINGLE array so they don't overwrite each other!
# In vascular_dashboard/urls.py
# Update your import string to include 'search_patient_api'


urlpatterns = [
    path('admin/', admin.site.urls),
    path('', home_dashboard, name='home_dashboard'),
    path('api/next-patient-id/', get_next_patient_id, name='get_next_patient_id'),
    path('api/save-patient/', save_patient, name='save_patient'),
    path('api/search-patient/', search_patient_api, name='search_patient_api'),
    
    # The new route for deleting records:
    path('api/delete-patient/', delete_patient_api, name='delete_patient_api'),

]