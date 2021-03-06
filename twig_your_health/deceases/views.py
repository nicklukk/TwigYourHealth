import random

from annoying.decorators import render_to
from django.contrib.auth.decorators import user_passes_test
from django.db.models import Q, Sum, Count, FloatField, ExpressionWrapper, F, IntegerField
from django.db.models.functions import Cast, Length
from django.http import JsonResponse, HttpResponseForbidden, HttpResponse
from django.shortcuts import get_object_or_404, render_to_response
from django.views.decorators.http import require_http_methods

from accounts.models import Relationships, DoctorSphere
from deceases.forms import PatientDeceaseForm
from deceases.models import Symptom, Decease, BodyPart, PatientDecease, Sphere
from notifications.views import add_message
from utils.checks import has_relationships


@render_to('deceases/diagnostics.html')
def diagnostics(request):
    body_symptoms = BodyPart.objects.all()
    return {'body_symptoms': body_symptoms}


@render_to('deceases/_tree.html')
def symptom_tree(request):
    body_part_id = request.GET.get('body_part_id')
    symptoms = Symptom.objects.filter(body_part__pk=body_part_id)
    return {'tree': symptoms}


def symptoms_autocomplete(request):
    input_name = request.GET.get('name').lower()  # sqllite quark
    symptoms = list(Symptom.objects.filter(Q(name__startswith=input_name) | Q(name__startswith=input_name.capitalize())) \
                    .values('id', 'name').order_by('name'))

    if len(symptoms) < 20:
        symptoms += list(
            Symptom.objects.exclude(Q(name__startswith=input_name) | Q(name__startswith=input_name.capitalize())) \
                .filter(Q(aliases__icontains=input_name) | Q(name__icontains=input_name)) \
                .values('id', 'name').order_by('name'))[:(20 - len(symptoms))]
    return JsonResponse(data=symptoms, safe=False)


@require_http_methods(["POST"])
@user_passes_test(lambda user: user.is_doctor)
def doctor_create_update_decease(request, pk=None):
    d = get_object_or_404(PatientDecease, pk=pk) if pk else None
    form = PatientDeceaseForm(request.POST, instance=d, auto_id=str(pk) + '_%s')

    if form.is_valid():
        decease = form.save(commit=False)
        doctor = request.user.doctor

        if not has_relationships(doctor.id, decease.patient.id):
            return HttpResponseForbidden('No relation ship between doctor and user')

        decease.author = request.user
        decease.decease = Decease.objects.get(name=form.cleaned_data['decease'])
        decease.save()

        add_message(
            message=f"<a href='{doctor.get_absolute_url()}'>{doctor.user.username}</a> has {'updated' if pk else 'created'} a new diagnos",
            owner=decease.patient.user)
        return HttpResponse('')
    return render_to_response('deceases/_doctor_create_update_patient_decease_form.html',
                              {'decease_form': form, 'pk': pk})


@render_to('deceases/_medical_records.html')
def medical_records(request, patient_id):
    access = False
    if request.user.is_patient:
        access = request.user.patient.id == patient_id
    elif request.user.is_doctor:
        access = Relationships.objects.filter(doctor=request.user.doctor, patient__pk=patient_id).exists()
    if not access:
        return HttpResponseForbidden('You are neither the patient or no relationships between doctor and user')
    medical_records = PatientDecease.objects.filter(patient__pk=patient_id).prefetch_related('symptoms',
                                                                                             'symptoms__symptom')
    for record in medical_records:
        record.form = PatientDeceaseForm(instance=record, initial={'decease': record.decease.name},
                                         auto_id=str(record.id) + '_%s')
    return {'medical_records': medical_records}


# @user_passes_test(lambda u: u.is_patient)
@render_to('deceases/_deceases_with_doctors.html')
def deceases_by_symptoms(request):

    symptoms_ids = request.GET.getlist('symptoms[]')
    symptoms = Symptom.objects.filter(pk__in=symptoms_ids).values_list('name', flat=True)
    symptoms_lookup = Q()
    for s in symptoms:
        symptoms_lookup |= Q(name__icontains=s[:-1])

    related_symptoms = Symptom.objects.filter(symptoms_lookup).values_list('id', flat=True)
    #  switch to distinct sum on postgres to get correct result
    whole_chance = Sum('deceasesymptom__chances')

    current_chance = Sum('deceasesymptom__chances', filter=Q(deceasesymptom__symptom__in=related_symptoms),
                         distinct=True)
    chance = Cast(current_chance, FloatField()) / Cast(whole_chance, FloatField()) * 100

    deceases = list(Decease.objects
                    .annotate(symptom_count=Count('deceasesymptom',
                                                  filter=Q(deceasesymptom__symptom__in=related_symptoms),
                                                  distinct=True))
                    .annotate(chance=chance)
                    .annotate(chance=ExpressionWrapper(F('chance') * F('symptom_count') /
                                                       len(symptoms_ids), output_field=IntegerField()))
                    .filter(~Q(chance=None))
                    .order_by()
                    .values('id', 'name', 'chance', 'number', 'sphere')[:10])



    deceases_with_doctors = []
    for ind, d in enumerate(deceases):
        chance = d['chance']
        number = d['number']
        deceases[ind]['chance'] = round(((chance * (100 / 2.27)) * (0.5 + ((number / 1000) ** 0.25))) ** 0.5)

    for d in sorted(deceases, key=lambda x: -x['chance']):
        sphere = d['sphere']
        doctors_sphere = (DoctorSphere.objects.filter(sphere__pk=sphere).select_related('doctor').order_by('?')[:1000])
        doctors_sphere = list(sorted(doctors_sphere, key=lambda x: x.rating))[:20]
        doctors = [ds.doctor for ds in doctors_sphere]
        random.shuffle(doctors)
        doctors = doctors[:3]
        deceases_with_doctors.append({"decease": d, "doctors": doctors})

    return {'deceases_with_doctors': deceases_with_doctors}


@render_to('deceases/_detail.html')
def decease_detail(request, pk):
    decease = get_object_or_404(Decease, pk=pk)
    return {'decease': decease, 'symptoms': decease.deceasesymptom_set.order_by('-chances')}


@render_to('deceases/list.html')
def decease_list(request):
    spheres = Sphere.objects.all().prefetch_related('decease_set')
    return {'spheres': spheres}


def decease_autocomplete(request):
    query = request.GET.get('query').lower()
    print(query)
    decease = list(Decease.objects.filter(Q(name__contains=query) |
                                          Q(name__startswith=query) |
                                          Q(name__startswith=query.capitalize())) \
                   .order_by(Length('name'))[:30])
    decease = [{"value": d.name, "data": d.id} for d in decease]
    return JsonResponse({"suggestions": decease})
