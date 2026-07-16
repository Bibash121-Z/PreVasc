from django.db import connection
import re
from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from .models import Patient
import json


# --- Block 1: Main web dashboard loader ---
# This block returns the basic web layout HTML file when you first load the page in a browser
def home_dashboard(request):
    return render(request, 'dashboard/index.html')
def get_next_patient_id(request):
    """
    Predicts the true next auto-increment ID by checking SQLite's internal sequence counter.
    """
    try:
        with connection.cursor() as cursor:
            # Query the internal sqlite sequence table for your patient model table name
            # Note: Django tables are usually named 'appname_modelname' (e.g., 'dashboard_patient')
            cursor.execute("SELECT seq FROM sqlite_sequence WHERE name='dashboard_patient' LIMIT 1")
            row = cursor.fetchone()
            
            if row:
                # If records have existed before, the next ID will be the last sequence + 1
                next_id = row[0] + 1
            else:
                # If the sequence table is empty (brand new DB), fallback to basic counting
                max_id = Patient.objects.order_by('-id').first()
                next_id = (max_id.id + 1) if max_id else 1
                
        return JsonResponse({'success': True, 'next_id': f"{next_id}"})
        
    except Exception as e:
        # Fallback safeguard in case table names differ
        max_id = Patient.objects.order_by('-id').first()
        next_id = (max_id.id + 1) if max_id else 1
        return JsonResponse({'success': True, 'next_id': f"{next_id}"})


@csrf_exempt # Exempt for basic development; secure with CSRF token in production
def save_patient(request):
    """
    Saves a registered patient to the database.
    """
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            patient = Patient.objects.create(
                name=data.get('name'),
                age=int(data.get('age')),
                gender=data.get('gender'),
                height=float(data.get('height'))
            )
            return JsonResponse({
                'success': True, 
                'patient_id': patient.id,
                'message': f"Patient {patient.id} registered successfully!"
            })
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=400)
            
    return JsonResponse({'error': 'Invalid request method'}, status=405)

# Add this to dashboard/views.py


def search_patient_api(request):
    """
    Looks up a patient from the DB by parsing the numerical ID out of the query string.
    """
    raw_query = request.GET.get('id', '').strip()
    if not raw_query:
        return JsonResponse({'success': False, 'error': 'Search field cannot be empty.'}, status=400)
    
    # Extract only the numbers from the text input field using Regex
    numeric_match = re.search(r'\d+', raw_query)
    if not numeric_match:
        return JsonResponse({'success': False, 'error': 'Invalid ID structure format.'}, status=400)
        
    extracted_id = int(numeric_match.group())

    try:
        patient = Patient.objects.get(id=extracted_id)
        return JsonResponse({
            'success': True,
            'data': {
                'id': f"PT-{patient.id}",
                'name': patient.name,
                'age': patient.age,
                'gender': patient.gender.capitalize(),
                'height': patient.height
            }
        })
    except Patient.DoesNotExist:
        return JsonResponse({'success': False, 'error': f'No patient record found for ID: PT-{extracted_id}'}, status=404)
    

#DELETE PATIENT REC
@csrf_exempt
def delete_patient_api(request):
    """
    Deletes a patient record from the DB using a POST request containing the Patient ID.
    """
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            raw_id = data.get('id', '')
            
            # Extract numbers from values like "PT-1" or "1"
            import re
            numeric_match = re.search(r'\d+', str(raw_id))
            if not numeric_match:
                return JsonResponse({'success': False, 'error': 'Invalid Patient ID format.'}, status=400)
                
            extracted_id = int(numeric_match.group())
            
            # Find and remove the record
            patient = Patient.objects.get(id=extracted_id)
            patient.delete()
            
            return JsonResponse({
                'success': True,
                'message': f"Patient PT-{extracted_id} has been permanently deleted."
            })
            
        except Patient.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Record not found in the database.'}, status=404)
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=400)
            
    return JsonResponse({'error': 'Invalid request method'}, status=405)