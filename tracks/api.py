from django.shortcuts import get_object_or_404, get_list_or_404
from django.db.utils import IntegrityError
from django.forms.models import model_to_dict

from time import perf_counter
from uuid import uuid4

from datetime import datetime, time, timedelta, date
from typing import List, Optional
from ninja import NinjaAPI, Schema

from tracks.models import *
from tracks import utils
from tracks import parameters

api = NinjaAPI()

class Detail(Schema):
    detail: str

# Representación abstracta de un turno, no tiene información
# de la fecha del turno
class PrimitiveShift(Schema):
    weekday: int
    block: str
    time: int # Tiempo transcurrido desde que comenzó el día en minutos

class _PrimitiveShift(Schema):
    block: int
    date: date

# Esto es la estructura base de un turno, independiente de si
# alguien lo ha hecho o no, y es una relación directa a los bloques.
class NaturalShift(Schema):
    block: str # Bloque al que está relacionado en turno
    checkin: datetime # Hora de entrada
    checkout: Optional[datetime] # Hora de salida

#Representa el bloque actual o el más cercano (si estamos en receso o almuerzo).
class UpcomingShift(NaturalShift):
    isactive: bool # Indica si estamos en el bloque o no

# La estructura base de un primo,
# contiene su información primordial.
class NaturalPrimo(Schema):
    mail: str
    nick: str

# Refiere a un turno comenzado por un primo
class RegisteredShift(NaturalShift):
    id: int # Id del turno
    primo: NaturalPrimo # El primo que registró este turno

class CurrentPrimo(NaturalPrimo):
    # Si el primo tiene algún turno corriendo (Sólo debería haber uno, ya
    # que si tienes un turno corriendo no te debería dejar inciar otro)
    running: Optional[RegisteredShift]
    # El actual o siguiente turno del primo, si hay un turno corriendo entonces
    # será el correspondiente a ese bloque para indicar el tiempo transcurrido
    next: NaturalShift

class Now(Schema):
    weekday: int # Día de la semana
    time: str # Horas y minutos
    datetime: datetime # Fecha completa

    # Actual o siguiente turno (Si es que ahora mismo no hay un turno activo)
    upcoming: UpcomingShift
    pair: List[NaturalPrimo] # Primos de turno

# Estadísticas de puntualidad de un primo
class Resume(Schema):
    start: datetime
    end: datetime

    # Número de turnos que el primo debió haber cumplido
    # correctamente durante el periodo de tiempo estudiado
    ideal: int

    inSchedule: List[RegisteredShift] # Turnos correctamente registrados
    # Turnos efectuados pero incoherentes; puede deberse a:
    # 1. No coincide con ningún turno del primo (Al momento de la llamada a la api)
    # 2. Cerrado temprano
    # 3. Cerrado tarde
    # 4. Nunca cerrado
    suspicious: List[RegisteredShift]

    datapoints: List[int]
    labels: List[str]

class PushShift(Schema):
    mail: str

class UpdateShift(Schema):
    id: int

@api.get('/test')
def test(_, mail: str, start: datetime):
    primo = get_object_or_404(Primo, mail=mail.lower())
    length, schedule = utils._parseSchedule(primo.schedule, start)
    for day in range(length*3):
        print(next(schedule))

@api.get("/now", response=Now)
def get_now_time(_):
    print('START GET /now', _u := uuid4(), utils.now().isoformat())
    _t = perf_counter()

    now = utils.now()
    upcoming = utils.aproximateToShift(now, False)
    pair = []
    for primo in Primo.objects.all():
        schedule = utils.parseSchedule(primo.schedule)
        if upcoming in schedule:
            pair.append(primo)

    _r = {
        "weekday": now.weekday(),
        "time": now.time().isoformat('minutes'),
        "datetime": now,
        
        "upcoming": {
            "block": upcoming.block.name,
            "checkin": upcoming.checkin,
            "checkout": upcoming.checkout,
            "isactive": (upcoming.checkin  - parameters.beforeStartTolerance) < utils.now() < (upcoming.checkin  + parameters.afterStartTolerance)
        },
        "pair": pair
    }
    
    print('END GET /now', _u, round(perf_counter() - _t))
    return _r

@api.get("/primos", response=List[NaturalPrimo])
def get_primos(_):
    print('START GET /primos', _u := uuid4(), utils.now().isoformat())
    _t = perf_counter()    

    _r = [{
        "mail": primo.mail,
        "nick": primo.nick
    } for primo in Primo.objects.all()]
    
    print('END GET /primos', _u, round(perf_counter() - _t))
    return _r

@api.get("/primos/{str:mail}", response=CurrentPrimo)
def get_primo(_, mail: str):
    print(_.get_full_path())
    print('START GET /primos', mail, _u := uuid4(), utils.now().isoformat())
    _t = perf_counter()

    primo = get_object_or_404(Primo, mail=mail.lower())
    try:
        rshift = StampedShift.objects.get(checkin__gte=utils.now().date(), primo=primo, checkout__isnull=True)
        nshift = utils.aproximateToShift(rshift.checkin)
        running = {
            "id": rshift.id,
            
            "primo": {
                "mail": primo.mail,
                "nick": primo.nick,
            },

            "block": nshift.block.name,

            "checkin": rshift.checkin,
            "checkout": rshift.checkout
        }
    except StampedShift.DoesNotExist:
        _, schedule = utils._parseSchedule(primo.schedule)
        nshift = next(schedule)# utils.parseSchedule(primo.schedule)[0]
        running = None

    _r = {
        "mail": primo.mail,
        "nick": primo.nick,
        
        "running": running,
        "next": {
            "block": nshift.block.name,
            "checkin": nshift.checkin,
            "checkout": nshift.checkout,
        }
    }

    print('END GET /primos', mail, _u, round(perf_counter() - _t))
    return _r

@api.get("/shifts")
def get_shifts(_, mail: str, start: date, end: date = None):
    print('START GET /shifts', mail, start, end, _u := uuid4(), utils.now().isoformat())
    _t = perf_counter()

    if end is None:
        end = utils.now().date()
    primo = get_object_or_404(Primo, mail=mail.lower())

    inSchedule, suspicious = [], []
    for stampedShift in StampedShift.objects.filter(checkin__gte=start, checkin__lte=end, primo=primo):
        shift = utils.aproximateToShift(stampedShift.checkin)
        fshift = model_to_dict(stampedShift)
        fshift["primo"] = {
            "mail": stampedShift.primo.mail,
            "nick": stampedShift.primo.nick,
        }
        fshift["block"] = shift.block.name

        rightCheckin = (shift.checkin - parameters.beforeStartTolerance) < fshift["checkin"] < (shift.checkin  + parameters.afterStartTolerance)
        rigthCheckout = (fshift["checkout"] is not None) and (shift.checkout < fshift["checkout"] < (shift.checkout + parameters.afterEndTolerance))
        if rightCheckin and rigthCheckout:
            inSchedule.append(fshift)
        else:
            suspicious.append(fshift)
    
    pardonedShifts = [utils.Shift(shift.date, parameters.Block[shift.block]) for shift in PardonedShift.objects.all()]
    _, schedule = utils._parseSchedule(primo.schedule, datetime.combine(start, time())) 
    datapoints, labels = [], []
    j, k = 0, 0
    while (shift := next(schedule)).date <= end:
        while k < len(pardonedShifts) and pardonedShifts[k] < shift:
            k += 1

        if k >= len(pardonedShifts) or shift != pardonedShifts[k]:
            labels.append(f"{parameters.days['mid'][shift.date.weekday()]} {shift.block.name}")
            if (
                    j < len(inSchedule)
                and shift.date == inSchedule[j]["checkin"].date()
                and shift.block.name == inSchedule[j]["block"]
            ):
                checkinTime = inSchedule[j]["checkin"].time()
                shiftStartTime = shift.block.start
                datapoints.append(60*(shiftStartTime.hour - checkinTime.hour) + shiftStartTime.minute - checkinTime.minute)
                j += 1
            else:
                datapoints.append(None)

    _r = {
        "start": start,
        "end": end,

        "ideal": len(datapoints),

        "inSchedule": inSchedule,
        "suspicious": suspicious,

        "datapoints": datapoints,
        "labels": labels,
    }

    print('END GET /shifts', mail, start, end, _u, round(perf_counter() - _t))
    return _r

@api.post("/shifts", response={200: RegisteredShift, 403: Detail})
def push_a_shift(_, payload: PushShift):
    print('START POST /shifts', payload, _u := uuid4(), utils.now().isoformat())
    _t = perf_counter()

    now = utils.now()
    primo = get_object_or_404(Primo, mail=payload.mail)
    shifts = utils.parseSchedule(primo.schedule)
    
    # Aquí se verifica si el turno que estás intentando pushear corresponde a alguno de los turnos de tu horario
    for shift in shifts:
        if (shift.checkin - parameters.beforeStartTolerance) < now < (shift.checkin + parameters.afterStartTolerance): #< (shift["checkout"] + parameters.afterEndTolerance):
            break
    else:
        return 403, {"detail": "You're not on your shift"}
    
    shift = StampedShift.objects.create(**{"primo": primo, "checkin": now})
    _r = 200, {
        "id": shift.id,

        "primo":  {
            "mail": primo.mail,
            "nick": primo.nick,
        },

        "block": utils.aproximateToShift(shift.checkin).block.name,
        
        "checkin": shift.checkin,
    }

    print('END POST /shifts', payload, _u, round(perf_counter() - _t))
    return _r

@api.get("/shifts/week", response=List[List[RegisteredShift]])
def get_week_shifts(_):
    print('START GET /shifts/week', _u := uuid4(), utils.now().isoformat())
    _t = perf_counter()

    now = utils.now()
    
    week = [[], [], [], [], []]
    for shift in StampedShift.objects.filter(checkin__gte=utils.firstWeekday()):
        week[shift.checkin.weekday()].append({
            "id": shift.id,
            
            "primo": {
                "mail": shift.primo.mail,
                "nick": shift.primo.nick,
            },

            "block": utils.aproximateToShift(shift.checkin).block.name,
            
            "checkin": shift.checkin,
            "checkout": shift.checkout,
        })

    # Esta parte del código se encarga de fusionar turnos consecutivos
    onemin = timedelta(minutes=1)
    for day in week:
        thisshift = 0
        while thisshift < len(day):
            nextshift = thisshift + 1
            while nextshift < len(day):
                if (day[thisshift]["checkout"] is None) or (day[nextshift]["checkin"] - day[thisshift]["checkout"]) > onemin:
                    # Ya que los turnos están ordenados se que esta condición se va a cumplir para todos los siguientes turnos
                    # NOTA: Releí este comentario ^^^ y lo entiendo para la primera condición, pero no para la segunda,
                    # valdría la pena revisarlo.
                    break
                if day[thisshift]["primo"] == day[nextshift]["primo"]:
                    # Fusiono dos turnos si la diferencia entre que finalizó uno y empezó otro es de menos de 1 minuto
                    day[thisshift]["checkout"] = day.pop(nextshift)["checkout"]    
                nextshift += 1
            thisshift += 1
    
    print('END GET /shifts/week', _u, round(perf_counter() - _t))
    return week

@api.put("/shifts", response={200: RegisteredShift, 403: Detail})
def update_a_shift(_, payload: UpdateShift):
    print('START PUT /shifts', payload, _u := uuid4(), utils.now().isoformat())
    _t = perf_counter()

    now = utils.now()
    shift = get_object_or_404(StampedShift, id=payload.id)

    if shift.checkin.date() != now.date():
        return 403, {"detail": "The check-in day is already over"}
    elif shift.checkout is not None:
        return 403, {"detail": "Shift already closed"}
    
    shift.checkout = now
    shift.save()
    
    _r = 200, {
        "id": shift.id,
        
        "primo": {
            "mail": shift.primo.mail,
            "nick": shift.primo.nick,
        },
        
        "block": utils.aproximateToShift(shift.checkin).block.name,

        "checkin": shift.checkin,
        "checkout": shift.checkout
    }

    print('END PUT /shifts', payload, _u, round(perf_counter() - _t))
    return _r

@api.post("/shifts/pardon", response={200: NaturalShift, 403: Detail})
def pardon_a_shift(_, payload: _PrimitiveShift):
    print('START POST /shifts/pardon', payload, _u := uuid4(), utils.now().isoformat())
    if 0 <= payload.block < len(parameters.Block):
        try:
            PardonedShift.objects.create(**payload.dict())
        except IntegrityError:
            return 403, {"detail": "Shift already pardoned"}

        block = parameters.Block[payload.block]
        _r = 200, {
            "block": block.name, 
            "checkin": datetime.combine(payload.date, block.start),
            "checkout": datetime.combine(payload.date, block.end)
        }
        
        print('END POST /shifts/pardon', payload, _u, round(perf_counter() - _t))
        return _r
    return 403, {"detail": f"Block ({payload.block}) out of the range (0..{len(parameters.Block) - 1})"}

