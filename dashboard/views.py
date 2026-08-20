from django.db import connection
import re
from django.utils import timezone
from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from .models import Patient, PatientFollowUp
import json


# --- Block 1: Main web dashboard loader ---
def home_dashboard(request):
    return render(request, 'dashboard/index.html')

def get_next_patient_id(request):
    """
    Predicts the true next auto-increment ID by checking SQLite's internal sequence counter.
    """
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT seq FROM sqlite_sequence WHERE name='dashboard_patient' LIMIT 1")
            row = cursor.fetchone()
            next_id = (row[0] + 1) if row else (Patient.objects.order_by('-id').first().id + 1 if Patient.objects.exists() else 1)
        return JsonResponse({'success': True, 'next_id': f"{next_id}"})
    except Exception:
        max_id = Patient.objects.order_by('-id').first()
        next_id = (max_id.id + 1) if max_id else 1
        return JsonResponse({'success': True, 'next_id': f"{next_id}"})


@csrf_exempt
def save_patient(request):
    """
    Saves a registered patient to the database.
    """
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            age = int(str(data.get('age', '')).strip())
            height = float(str(data.get('height', '')).strip())

            if age < 0 or height < 0:
                return JsonResponse({'success': False, 'error': 'Age and Height must be non-negative.'}, status=400)

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


def search_patient_api(request):
    """
    Looks up a patient from the DB and returns their full profile and history.
    """
    raw_query = request.GET.get('id', '').strip()
    if not raw_query:
        return JsonResponse({'success': False, 'error': 'Search field cannot be empty.'}, status=400)
    
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
            try:
                return round(float(value), digits)
            except (ValueError, TypeError):
                return '--'

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
                'sbp': _fmt_num(row.sbp, 1),
                'dbp': _fmt_num(row.dbp, 1), 
            }
            for row in followups
        ]

        return JsonResponse({
            'success': True,
            'data': {
                'id': f"PT-{patient.id}",
                'name': patient.name,
                'phone_no': patient.phone_no or '--',
                'age': patient.age,
                'gender': str(patient.gender).capitalize(),
                'height': patient.height,
                'registered_at': timezone.localtime(patient.created_at).strftime('%Y-%m-%d') if patient.created_at else '--',
                'heart_rate': patient.heart_rate if patient.heart_rate else '--',
                'followups': followup_rows
            }
        })
    except Patient.DoesNotExist:
        return JsonResponse({'success': False, 'error': f'No patient record found for ID: PT-{extracted_id}'}, status=404)


@csrf_exempt
def delete_patient_api(request):
    """
    Deletes a patient record from the DB.
    """
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            raw_id = data.get('id', '')
            numeric_match = re.search(r'\d+', str(raw_id))
            if not numeric_match:
                return JsonResponse({'success': False, 'error': 'Invalid Patient ID format.'}, status=400)
                
            extracted_id = int(numeric_match.group())
            patient = Patient.objects.get(id=extracted_id)
            patient.delete()
            
            return JsonResponse({'success': True, 'message': f"Patient PT-{extracted_id} has been permanently deleted."})
        except Patient.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Record not found in the database.'}, status=404)
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=400)
            
    return JsonResponse({'error': 'Invalid request method'}, status=405)


@csrf_exempt
def save_patient_heart_rate(request):
    """
    Saves the entire session diagnostic report (HR, BP, PWV, Risk, AI Features) to the database.
    """
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            raw_id = data.get('patient_id', '')
            requested_hr = data.get('heart_rate')
            features_payload = data.get('features') if isinstance(data.get('features'), dict) else {}
            
            numeric_match = re.search(r'\d+', str(raw_id))
            if not numeric_match:
                return JsonResponse({'success': False, 'error': 'Invalid Patient ID format.'}, status=400)
                
            extracted_id = int(numeric_match.group())

            live_hr = None
            try:
                if requested_hr is not None and float(requested_hr) > 0:
                    live_hr = float(requested_hr)
            except (TypeError, ValueError):
                live_hr = None

            if live_hr is None:
                from .mqtt_worker import get_latest_bpm
                live_hr = get_latest_bpm()

            if live_hr is None or live_hr <= 0:
                return JsonResponse({'success': False, 'error': 'No valid live heart rate available yet. Start capture first.'}, status=400)
            
            patient = Patient.objects.get(id=extracted_id)
            patient.heart_rate = round(float(live_hr), 1)
            patient.save()

            # Case-insensitive feature extractor helper
            def get_f(key, default=None):
                return features_payload.get(key) or features_payload.get(key.lower()) or features_payload.get(key.upper()) or default

            raw_risk = get_f('cvd_risk')
            risk_label = "HIGH RISK" if raw_risk == 1 else ("LOW RISK" if raw_risk == 0 else str(raw_risk or '--'))

            followup = PatientFollowUp.objects.create(
                patient=patient,
                heart_rate=patient.heart_rate,
                sbp=get_f('sbp'),  # <--- NEW
                dbp=get_f('dbp'),  # <--- NEW
                si=get_f('si') or get_f('SI'),
                cvd_risk=risk_label,
                cvd_age=get_f('cvd_age'),
                pwv=get_f('pwv'),
                ct=get_f('ct') or get_f('CT'),
                ri=get_f('ri') or get_f('RI'),
                dpdt_max=get_f('dpdt_max'),
                agi_mod=get_f('agi_mod') or get_f('AGI_mod'),
                lvet=get_f('lvet') or get_f('LVET'),
                ppg_sevr=get_f('ppg_sevr') or get_f('PPG_SEVR'),
                ppg_asys=get_f('ppg_asys') or get_f('PPG_Asys'),
                ppg_adia=get_f('ppg_adia') or get_f('PPG_Adia'),
                pat=get_f('pat') or get_f('PAT'),
            )
            
            return JsonResponse({
                'success': True, 
                'saved_heart_rate': patient.heart_rate,
                'followup_id': followup.id,
                'message': f"Diagnostic session saved successfully for PT-{extracted_id}!"
            })
            
        except Patient.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Patient record profile not found.'}, status=404)
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=400)
            
    return JsonResponse({'error': 'Invalid request method'}, status=405)