from datetime import datetime, timedelta
from time import time
from typing import List, Optional
from ninja import NinjaAPI, Schema
from django.shortcuts import get_object_or_404, get_list_or_404

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

class SheduleShift(Schema):
    weekday: int
    block: str
    time: int # Tiempo transcurrido desde que comenzó el día en minutos

# Estadísticas de puntualidad de un primo
class Resume(Schema):
    start: datetime
    end: datetime

    # Horario del primo, sin fecha específica
    schedule: List[SheduleShift]
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
        
    upcoming["isactive"] = (upcoming["checkin"]  - parameters.beforeStartTolerance) < utils.now() < (upcoming["checkin"]  + parameters.afterStartTolerance)

    return {
        "weekday": now.weekday(),
        "time": f"{now.hour:02d}:{now.minute:02d}",
        "datetime": now,
        
        "upcoming": upcoming,
        "pair": pair
    }

@api.get("/primos", response=List[NaturalPrimo])
def get_primos(_):
    return [{
        "mail": primo.mail,
        "nick": primo.nick
    } for primo in get_list_or_404(Primo)]

@api.get("/primos/{str:mail}", response=CurrentPrimo)
def get_primo(_, mail: str):
    primo = get_object_or_404(Primo, mail=mail.lower())
    try:
        rshift = Shift.objects.get(checkin__gte=utils.now().date(), primo=primo, checkout__isnull=True)
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

# Esta función te retorna un resumen de todos los turnos de un primo en un intervalo de tiempo
# Es importante que <start> y <end> no vengan con información de zona horaria
@api.get("/shifts", response=Resume)
def get_shifts(_, mail: str, start: datetime, end: datetime = None):
    if end == None:
        end = utils.now()
    start = start.replace(tzinfo=None)
    end = end.replace(tzinfo=None)
    
    primo = get_object_or_404(Primo, mail=mail.lower())

    schedule = utils.parseSchedule(primo.schedule, reference=start)
    ideal = (weeks := (end - start).days//7)*len(schedule)
    curr = start + timedelta(days=weeks*7)
    for shift in schedule:
        checkin = shift["checkin"]
        curr += timedelta(days=(checkin.weekday() - curr.weekday())%7, hours=checkin.hour - curr.hour, minutes=checkin.minute - curr.minute)
        if curr > end:
            break
        ideal += 1
    
    inSchedule, suspicious = [], []
    for shift in Shift.objects.filter(checkin__gte=start, checkin__lte=end, primo=primo).order_by('checkin'):
        block = utils.aproximateToBlock(shift.checkin)
        fshift = {
            "id": shift.id,
            
            "primo": {
                "mail": shift.primo.mail,
                "nick": shift.primo.nick,
            },

            "block": block["block"],
            
            "checkin": shift.checkin,
            "checkout": shift.checkout,
        }

        rightCheckin = (block["checkin"] - parameters.beforeStartTolerance) < fshift["checkin"] < (block["checkin"]  + parameters.afterStartTolerance)
        rigthCheckout = (fshift["checkout"] != None) and (block["checkout"] < fshift["checkout"] < (block["checkout"] + parameters.afterEndTolerance))
        if rightCheckin and rigthCheckout:
            inSchedule.append(fshift)
        else:
            suspicious.append(fshift)
    
    return {
        "start": start,
        "end": end,

        "schedule": list(map(lambda s: {
            "weekday": s["checkin"].weekday(),
            "block": s["block"],
            "time": 60*s["checkin"].hour + s["checkin"].minute
        }, schedule)),
        "ideal": ideal,

        "inSchedule": inSchedule,
        "suspicious": suspicious
    }

@api.post("/shifts", response={200: RegisteredShift, 403: Detail})
def push_a_shift(_, payload: PushShift):
    now = utils.now()
    primo = get_object_or_404(Primo, mail=payload.mail)
    shifts = utils.parseSchedule(primo.schedule)
    
    # Aquí se verifica si el turno que estás intentando pushear corresponde a alguno de los turnos de tu horario
    for shift in shifts:
        if (shift["checkin"] - parameters.beforeStartTolerance) < now < (shift["checkin"] + parameters.afterStartTolerance): #< (shift["checkout"] + parameters.afterEndTolerance):
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

@api.get("/shifts/week", response=List[List[RegisteredShift]])
def get_week_shifts(_):
    now = utils.now()
    
    week = [[], [], [], [], []]
    for shift in Shift.objects.filter(checkin__gte=utils.firstWeekday()).order_by('checkin'):
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
                    # NOTA: Releí este comentario ^^^ y lo entiendo para la primera condición, pero no para la segunda,
                    # valdría la pena revisarlo.
                    break
                if day[thisshift]["primo"] == day[nextshift]["primo"]:
                    # Fusiono dos turnos si la diferencia entre que finalizó uno y empezó otro es de menos de 1 minuto
                    day[thisshift]["checkout"] = day.pop(nextshift)["checkout"]    
                nextshift += 1
            thisshift += 1

    return week

@api.put("/shifts", response={200: RegisteredShift, 403: Detail})
def update_a_shift(_, payload: UpdateShift):
    now = utils.now()
    shift = get_object_or_404(Shift, id=payload.id)

    if shift.checkin.date() != now.date():
        return 403, {"detail": "The check-in day is already over"}
    elif shift.checkout != None:
        return 403, {"detail": "Shift already closed"}
    
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

#@api.post("/shifts/pardon", response={200: RegisteredShift, 403: Detail})
#def pardon_a_shift(_, payload: )
