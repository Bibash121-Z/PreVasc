from django.db import connection
import re
from django.utils import timezone
from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from .models import Patient, PatientFollowUp
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
            age = int(str(data.get('age', '')).strip())
            height = float(str(data.get('height', '')).strip())

            if age < 0:
                return JsonResponse({'success': False, 'error': 'Age cannot be negative.'}, status=400)

            if height < 0:
                return JsonResponse({'success': False, 'error': 'Height cannot be negative.'}, status=400)

            patient = Patient.objects.create(
                name=data.get('name'),
                phone_no=data.get('phone_no'),
                age=age,
                gender=data.get('gender'),
                height=height
            )
            return JsonResponse({
                'success': True, 
                'patient_id': patient.id,
                'registered_at': timezone.localtime(patient.created_at).strftime('%Y-%m-%d') if patient.created_at else '--',
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
        followups = patient.followups.order_by('-created_at')

        def _fmt_num(value, digits=2):
            if value is None:
                return '--'
            return round(float(value), digits)

        followup_rows = [
            {
                'id': row.id,
                'date': timezone.localtime(row.created_at).strftime('%Y-%m-%d %H:%M') if row.created_at else '--',
                'hr': _fmt_num(row.heart_rate, 1),
                'si': _fmt_num(row.si, 2),
                'cvd_risk': row.cvd_risk or '--',
                'cvd_age': _fmt_num(row.cvd_age, 1),
                'pwv': _fmt_num(row.pwv, 2),
                'ct': _fmt_num(row.ct, 2),
                'ri': _fmt_num(row.ri, 3),
                'dpdt_max': _fmt_num(row.dpdt_max, 3),
                'agi_mod': _fmt_num(row.agi_mod, 3),
                'lvet': _fmt_num(row.lvet, 2),
                'ppg_sevr': _fmt_num(row.ppg_sevr, 3),
                'ppg_asys': _fmt_num(row.ppg_asys, 3),
                'ppg_adia': _fmt_num(row.ppg_adia, 3),
                'pat': _fmt_num(row.pat, 2),
            }
            for row in followups
        ]

        return JsonResponse({
            'success': True,
            'data': {
                'id': f"PT-{patient.id}",
                'name': patient.name,
                'phone_no': patient.phone_no,
                'age': patient.age,
                'gender': patient.gender.capitalize(),
                'height': patient.height,
                'registered_at': timezone.localtime(patient.created_at).strftime('%Y-%m-%d') if patient.created_at else '--',
                
                # --- THIS IS THE NEW LINE WE ADDED BESIDE THE REST ---
                'heart_rate': patient.heart_rate if patient.heart_rate else '--',
                'followups': followup_rows
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

@csrf_exempt
def save_patient_heart_rate(request):
    """
    Updates an existing patient's record with their calculated Heart Rate (BPM).
    """
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            raw_id = data.get('patient_id', '')
            requested_hr = data.get('heart_rate')
            features_payload = data.get('features') if isinstance(data.get('features'), dict) else {}
            
            # Reusing your clean regex logic to extract the absolute integer ID
            numeric_match = re.search(r'\d+', str(raw_id))
            if not numeric_match:
                return JsonResponse({'success': False, 'error': 'Invalid Patient ID format.'}, status=400)
                
            extracted_id = int(numeric_match.group())

            live_hr = None
            try:
                if requested_hr is not None:
                    parsed_hr = float(requested_hr)
                    if parsed_hr > 0:
                        live_hr = parsed_hr
            except (TypeError, ValueError):
                live_hr = None

            if live_hr is None:
                from .mqtt_worker import get_latest_bpm
                live_hr = get_latest_bpm()

            if live_hr is None or live_hr <= 0:
                return JsonResponse(
                    {
                        'success': False,
                        'error': 'No valid live heart rate is available yet. Start capture and wait for stable BPM.'
                    },
                    status=400
                )
            
            # Look up the registered profile row, modify just the heart rate cell, and save
            patient = Patient.objects.get(id=extracted_id)
            patient.heart_rate = round(float(live_hr), 1)
            patient.save()

            followup = PatientFollowUp.objects.create(
                patient=patient,
                heart_rate=patient.heart_rate,
                si=features_payload.get('si'),
                cvd_risk=features_payload.get('cvd_risk'),
                cvd_age=features_payload.get('cvd_age'),
                pwv=features_payload.get('pwv'),
                ct=features_payload.get('ct'),
                ri=features_payload.get('ri'),
                dpdt_max=features_payload.get('dpdt_max'),
                agi_mod=features_payload.get('agi_mod'),
                lvet=features_payload.get('lvet'),
                ppg_sevr=features_payload.get('ppg_sevr'),
                ppg_asys=features_payload.get('ppg_asys'),
                ppg_adia=features_payload.get('ppg_adia'),
                pat=features_payload.get('pat'),
            )
            
            return JsonResponse({
                'success': True, 
                'saved_heart_rate': patient.heart_rate,
                'followup_id': followup.id,
                'message': f"Heart rate of {patient.heart_rate} BPM updated successfully for PT-{extracted_id}!"
            })
            
        except Patient.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Patient record profile not found.'}, status=404)
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=400)
            
    return JsonResponse({'error': 'Invalid request method'}, status=405)