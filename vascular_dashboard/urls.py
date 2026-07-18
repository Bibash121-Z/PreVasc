from django.contrib import admin
from django.urls import path
# Import ALL your custom functions from your local dashboard views file
from dashboard.views import (
    home_dashboard, 
    get_next_patient_id, 
    save_patient, 
    search_patient_api, 
    delete_patient_api,
    save_patient_heart_rate  # <-- ADDED THIS IMPORT HERE
)

# --- Combined Master URL Map ---
urlpatterns = [
    path('admin/', admin.site.urls),
    path('', home_dashboard, name='home_dashboard'),
    path('api/next-patient-id/', get_next_patient_id, name='get_next_patient_id'),
    path('api/save-patient/', save_patient, name='save_patient'),
    path('api/search-patient/', search_patient_api, name='search_patient_api'),
    path('api/delete-patient/', delete_patient_api, name='delete_patient_api'),
    
    # --- REMOVED "views." PREFIX HERE ---
    path('api/save-heart-rate/', save_patient_heart_rate, name='save_patient_heart_rate'),
]