from datetime import datetime, timedelta
from typing import List, Optional
from ninja import NinjaAPI, Schema
from django.shortcuts import get_list_or_404, get_object_or_404

from tracks.models import *
from tracks import utils
from tracks import parameters

api = NinjaAPI()

class Detail(Schema):
    detail: str

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

class PushShift(Schema):
    mail: str

class UpdateShift(Schema):
    id: int

@api.get("/now", response=Now)
def get_now_time(_):
    now = utils.now()
    
    upcoming = utils.upcomingShift()
    pair = []
    for primo in Primo.objects.all():
        schedule = utils.parseSchedule(primo.schedule)
        if upcoming in schedule:
            pair.append(primo)
        
    # Dejo toterancia al principio para que puedas empezar el turno antes,
    # pero no al final porque podrías iniciar un turno cuando el bloque ya terminó
    upcoming["isactive"] = (upcoming["checkin"]  - parameters.tolerance) < utils.now() < upcoming["checkout"]

    return {
        "weekday": now.weekday(),
        "time": f"{now.hour:02d}:{now.minute:02d}",
        "datetime": now,
        
        "upcoming": upcoming,
        "pair": pair
    }

@api.get("/primos/{str:mail}", response=CurrentPrimo)
def get_primo(_, mail: str):
    primo = get_object_or_404(Primo, mail=mail.lower())
    firstHour = utils.now().replace(hour=0, minute=0, second=0, microsecond=0)
    try:
        rshift = Shift.objects.get(checkin__gt=firstHour, primo=primo, checkout__isnull=True)
        nshift = utils.aproximateToBlock(rshift.checkin)
        running = {
            "id": rshift.id,
            
            "primo": {
                "mail": primo.mail,
                "nick": primo.nick,
            },

            "block": nshift["block"],

            "checkin": rshift.checkin,
            "checkout": rshift.checkout
        }
    except Shift.DoesNotExist:
        nshift = utils.parseSchedule(primo.schedule)[0]
        running = None

    return {
        "mail": primo.mail,
        "nick": primo.nick,
        
        "running": running,
        "next": nshift
    }

# Retorna todos los turnos que han habido, de forma histórica.
@api.get("/shifts", response=List[RegisteredShift])
def get_shifts(_):
    return [{
        "id": shift.id,
        
        "primo": {
            "mail": shift.primo.mail,
            "nick": shift.primo.nick,
        },

        "block": utils.aproximateToBlock(shift.checkin)["block"],
        
        "checkin": shift.checkin,
        "checkout": shift.checkout,
    } for shift in Shift.objects.all()]

@api.post("/shifts", response={200: RegisteredShift, 403: Detail})
def push_a_shift(_, payload: PushShift):
    now = utils.now()
    primo = get_object_or_404(Primo, mail=payload.mail)
    shifts = utils.parseSchedule(primo.schedule)
    
    for shift in shifts:
        if (shift["checkin"] - parameters.tolerance) < now < (shift["checkout"] + parameters.tolerance):
            break
    else:
        return 403, {"detail": "You're not on your shift"}
    
    shift = Shift.objects.create(**{"primo": primo, "checkin": now})
    return 200, {
        "id": shift.id,

        "primo":  {
            "mail": primo.mail,
            "nick": primo.nick,
        },

        "block": utils.aproximateToBlock(shift.checkin)["block"],
        
        "checkin": shift.checkin,
    }

#@api.post("/DEBUGshifts")
#def push_a_shift_debug(_, payload: RegisteredShift):
#    primo = get_object_or_404(Primo, mail=payload.mail)
#    shift = Shift.objects.create(**{
#        "primo": primo,
#        "checkin": payload.checkin,
#        "checkout": payload.checkout
#    })
#    return 200, {
#        "id": shift.id,
#        
#        "rol": payload.rol,
#        
#        "checkin": shift.checkin,
#    }

@api.get("/shifts/week", response=List[List[RegisteredShift]])
def get_week_shifts(_):
    now = utils.now()
    
    week = [[], [], [], [], []]
    for shift in Shift.objects.filter(checkin__gt=utils.firstWeekday()).order_by('checkin'):
        week[shift.checkin.weekday()].append({
            "id": shift.id,
            
            "primo": {
                "mail": shift.primo.mail,
                "nick": shift.primo.nick,
            },

            "block": utils.aproximateToBlock(shift.checkin)["block"],
            
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
                if (day[thisshift]["checkout"] == None) or (day[nextshift]["checkin"] - day[thisshift]["checkout"]) > onemin:
                    # Ya que los turnos están ordenados se que esta condición se va a cumplir para todos los siguientes turnos
                    break
                elif day[thisshift]["primo"] == day[nextshift]["primo"]:
                    # Fusiono dos turnos si la diferencia entre que finalizó uno y empezó otro es de menos de 1 minuto
                    day[thisshift]["checkout"] = day.pop(nextshift)["checkout"]    
                nextshift += 1
            thisshift += 1

    return week

@api.get("/shifts/{str:mail}", response=List[RegisteredShift])
def get_shifts_by_mail(_, mail: str):
    shifts = get_list_or_404(Shift, primo=mail)
    return [{
        "id": shift.id,
        
        "primo": {
            "mail": shift.primo.mail,
            "nick": shift.primo.nick,
        },

        "block": utils.aproximateToBlock(shift.checkin)["block"],
        
        "checkin": shift.checkin,
        "checkout": shift.checkout,
    } for shift in shifts]

@api.put("/shifts", response={200: RegisteredShift, 403: Detail})
def update_a_shift(_, payload: UpdateShift):
    now = utils.now()
    shift = get_object_or_404(Shift, id=payload.id)
    if shift.checkin.date() != now.date():
        return 403, {"detail": "The check-in day is already over"}
    
    shift.checkout = now
    shift.save()
    return 200, {
        "id": shift.id,
        
        "primo": {
            "mail": shift.primo.mail,
            "nick": shift.primo.nick,
        },
        
        "block": utils.aproximateToBlock(shift.checkin)["block"],

        "checkin": shift.checkin,
        "checkout": shift.checkout
    }
