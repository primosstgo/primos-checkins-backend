# Django
from django.shortcuts import get_object_or_404
from django.db.utils import IntegrityError
from django.forms.models import model_to_dict
from ninja import NinjaAPI, Schema
# Classes & Typing
from datetime import datetime, time, timedelta, date
from typing import List, Optional

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

@api.get("/now", response=Now)
@utils.logged
def get_now_time(_):
    now = utils.now()
    upcoming = utils.aproximateToShift(now, False)
    pair = []
    for primo in Primo.objects.all():
        schedule = utils.DEPRECATED_parseSchedule(primo.schedule)
        if upcoming in schedule:
            pair.append(primo)

    return 200, {
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

@api.get("/primos", response=List[NaturalPrimo])
@utils.logged
def get_primos(_):
    return 200, [{
        "mail": primo.mail,
        "nick": primo.nick
    } for primo in Primo.objects.all()]

@api.get("/primos/{str:mail}", response=CurrentPrimo)
@utils.logged
def get_primo(_, mail: str):
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
        _, schedule = utils.parseSchedule(primo.schedule)
        nshift = next(schedule)# utils.DEPRECATED_parseSchedule(primo.schedule)[0]
        running = None

    return 200, {
        "mail": primo.mail,
        "nick": primo.nick,
        
        "running": running,
        "next": {
            "block": nshift.block.name,
            "checkin": nshift.checkin,
            "checkout": nshift.checkout,
        }
    }

@api.get("/shifts")
@utils.logged
def get_shifts(_, mail: str, start: date, end: date | None = None):
    if end is None:
        end = utils.now().date()
    primo = get_object_or_404(Primo, mail=mail.lower())

    inSchedule, suspicious = [], []
    for stampedShift in StampedShift.objects.filter(checkin__gte=start, checkin__lte=end, primo=primo):
        shift = utils.aproximateToShift(stampedShift.checkin)
        fshift = model_to_dict(stampedShift)
        fshift.update({
            "primo": {
                "mail": stampedShift.primo.mail,
                "nick": stampedShift.primo.nick,
            },
            "block": shift.block.name,
            "start": datetime.combine(shift.day, shift.block.start),
            "end": datetime.combine(shift.day, shift.block.end),
        })

        rightCheckin = (shift.checkin - parameters.beforeStartTolerance) < fshift["checkin"] < (shift.checkin  + parameters.afterStartTolerance)
        rigthCheckout = (fshift["checkout"] is not None) and (shift.checkout < fshift["checkout"] < (shift.checkout + parameters.afterEndTolerance))
        if rightCheckin and rigthCheckout:
            inSchedule.append(fshift)
        else:
            suspicious.append(fshift)
    
    pardonedShifts = [utils.Shift(shift.date, parameters.Block[shift.block]) for shift in PardonedShift.objects.all()]
    _, schedule = utils.parseSchedule(primo.schedule, datetime.combine(start, time())) 
    datapoints, labels, shifts = [], [], []
    j, k = 0, 0
    while (shift := next(schedule)).day <= end:
        while k < len(pardonedShifts) and pardonedShifts[k] < shift:
            k += 1

        if k >= len(pardonedShifts) or shift != pardonedShifts[k]:
            labels.append(f"{parameters.days['mid'][shift.day.weekday()]} {shift.block.name}")
            if (
                    j < len(inSchedule)
                and shift.day == inSchedule[j]["checkin"].date()
                and shift.block.name == inSchedule[j]["block"]
            ):
                checkinTime = inSchedule[j]["checkin"].time()
                shiftStartTime = shift.block.start
                datapoints.append(60*(shiftStartTime.hour - checkinTime.hour) + shiftStartTime.minute - checkinTime.minute)

                shifts.append(inSchedule[j])

                j += 1
            else:
                datapoints.append(None)
                shifts.append({
                    "id": None,
                    "primo": None,

                    "checkin": None,
                    "checkout": None,
                    
                    "block": shift.block.name,
                    "start": datetime.combine(shift.day, shift.block.start),
                    "end": datetime.combine(shift.day, shift.block.end),
                })

    return 200, {
        "primo": {
            "mail": primo.mail,
            "nick": primo.nick,
        },
        "start": start,
        "end": end,

        "shifts": shifts,

        #"stamped": inSchedule,
        "suspicious": suspicious,

        "datapoints": datapoints,
        "labels": labels,
    }

@api.post("/shifts", response={200: RegisteredShift, 403: Detail})
@utils.logged
def push_a_shift(_, payload: PushShift):
    now = utils.now()
    primo = get_object_or_404(Primo, mail=payload.mail)
    shifts = utils.DEPRECATED_parseSchedule(primo.schedule)
    
    # Aquí se verifica si el turno que estás intentando pushear corresponde a alguno de los turnos de tu horario
    for shift in shifts:
        if (shift.checkin - parameters.beforeStartTolerance) < now < (shift.checkin + parameters.afterStartTolerance): #< (shift["checkout"] + parameters.afterEndTolerance):
            break
    else:
        return 403, {"detail": "You're not on your shift"}
    
    shift = StampedShift.objects.create(**{"primo": primo, "checkin": now})
    return 200, {
        "id": shift.id,

        "primo":  {
            "mail": primo.mail,
            "nick": primo.nick,
        },

        "block": utils.aproximateToShift(shift.checkin).block.name,
        
        "checkin": shift.checkin,
    }

@api.get("/shifts/week", response=List[List[RegisteredShift]])
@utils.logged
def get_week_shifts(_):
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
    
    return 200, week

@api.put("/shifts", response={200: RegisteredShift, 403: Detail})
@utils.logged
def update_a_shift(_, payload: UpdateShift):
    now = utils.now()
    shift = get_object_or_404(StampedShift, id=payload.id)

    if shift.checkin.date() != now.date():
        return 403, {"detail": "The check-in day is already over"}
    elif shift.checkout is not None:
        return 403, {"detail": "Shift already closed"}
    
    shift.checkout = now
    shift.save()
    
    return 200, {
        "id": shift.id,
        
        "primo": {
            "mail": shift.primo.mail,
            "nick": shift.primo.nick,
        },
        
        "block": utils.aproximateToShift(shift.checkin).block.name,

        "checkin": shift.checkin,
        "checkout": shift.checkout
    }

@api.post("/shifts/pardon", response={200: NaturalShift, 403: Detail})
@utils.logged
def pardon_a_shift(_, payload: _PrimitiveShift):
    if 0 <= payload.block < len(parameters.Block):
        try:
            PardonedShift.objects.create(**payload.dict())
        except IntegrityError:
            return 403, {"detail": "Shift already pardoned"}

        block = parameters.Block[payload.block]
        return 200, {
            "block": block.name, 
            "checkin": datetime.combine(payload.date, block.start),
            "checkout": datetime.combine(payload.date, block.end)
        }
    return 403, {"detail": f"Block ({payload.block}) out of the range (0..{len(parameters.Block) - 1})"}
