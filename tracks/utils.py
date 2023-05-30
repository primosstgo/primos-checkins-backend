from datetime import date, datetime, timedelta
from re import findall, fullmatch
from typing import List, NamedTuple, Callable

from time import perf_counter
from uuid import uuid4
from functools import wraps

from tracks import parameters

# Decorator que imprime un log cuando se haga una llamada a la api
def logged(api_call: Callable):
    @wraps(api_call)
    def wrap(request, *args, **kwargs):
        print(f'{(key := uuid4())} IN  {request.method} {request.get_full_path()}')
        time_counter, response_code, response_body = perf_counter(), *api_call(request, *args, **kwargs)
        print(f'{key} OUT {response_code} {(perf_counter() - time_counter)*1000:03.0f}ms')
        return response_code, response_body
    return wrap

# Esta función es importante para el debug, ya que nos
# permite cambiar fácilmente la hora en toda la app.
def now():
    return datetime.now()#.replace(day=9, hour=9, minute=26, second=0, microsecond=0)

def firstWeekday(reference: datetime | None = None) -> date:
    if reference is None:
        reference = now()
    return reference.date() - timedelta(days=reference.weekday())

# Esta función te retorna el regex que procesa el horario de un primo
# NOTA: Quiero mover esto a parameters.py
def getRegex():
    lastShift = len(parameters.Block) - 1
    return f"([{parameters.days['short']}](?:[0-{lastShift}],)*[0-{lastShift}])"

def verifyRegex(schedule: str) -> bool:
    return fullmatch(f'{getRegex()}+', schedule) is not None

class Shift(NamedTuple):
    date: date
    block: parameters.Block

    def __repr__(self) -> str:
        return f'{self.date.isoformat()} {self.block.name}'

    @property
    def checkin(self) -> datetime:
        return datetime.combine(self.date, self.block.start)

    @property
    def checkout(self) -> datetime:
        return datetime.combine(self.date, self.block.end)

# DEPRECATED!: Usar parseSchedule en su lugar. No lo borro porque no sé si
#              ciertas partes del código funcionarían sin esta función, pero la
#              idea sería borrar esta función.
# Retorna el horario del primo, ordenado desde el turno actual (desde el punto de
# referencia <reference>) o el más cercano, hasta el más lejano.
# NOTA1: Debería retornar un objeto Block y un Date
# NOTA2: Acabo de leer la NOTA1 y no tengo idea a qué me refería cuando la escribí
# NOTA3: DEPRECATED
def DEPRECATED_parseSchedule(schedule: str, reference: datetime | None = None) -> List[Shift]:
    if reference is None:
        reference = now()
    shifts = []
    
    for daily in findall(getRegex(), schedule):
        for i in daily[1:].split(','):
            block = parameters.Block[int(i)]
            checkout = datetime.combine(firstWeekday(reference), block.end) + timedelta(days=parameters.days['short'].index(daily[0]))
            # Si el turno de esta semana ya terminó, entonces lo tiro para la
            # próxima semana
            if checkout < reference:
                checkout += timedelta(days=7)
            shifts.append(Shift(checkout.date(), block))
    
    shifts.sort(key=lambda s: datetime.combine(s.date, s.block.start))
    return shifts

# Esta función te retorna un generator que genera tu próximo turno a partir de una
# referencia <reference>.
# https://docs.python.org/3/reference/expressions.html#yield-expressions
# NOTA: Programé esta función pensando en nunca usarla directamente (por eso parte
# por _), la uso sólo en parseSchedule.
def _scheduleGenerator(schedule, reference: datetime):
    i = 0
    monday = firstWeekday(reference)
    for weekday, block in schedule:
        checkout = datetime.combine(monday, block.end) + timedelta(days=weekday)
        if checkout >= reference:
            break
        i += 1
    else:
        i = 0
        monday += timedelta(days=7)
    
    while True:
        weekday, block = schedule[i]
        yield Shift(monday + timedelta(days=weekday), block)
        if not (i := (i + 1)%len(schedule)):
            monday += timedelta(days=7)

# Esta función, a partir de un horario <schedule> en el formato del regex, retorna
# el largo del horario de un Primo (cantidad de turnos por semana) y un generator de
# los próximos turnos a partir de una referencia <reference>. 
def parseSchedule(schedule: str, reference: datetime | None = None):
    if reference is None:
        reference = now()
    
    effectiveSchedule = []
    for daily in findall(getRegex(), schedule):
        for i in daily[1:].split(','):
            block = parameters.Block[int(i)]
            weekday = parameters.days['short'].index(daily[0])
            effectiveSchedule.append((weekday, block))
    
    return (len(effectiveSchedule), _scheduleGenerator(effectiveSchedule, reference))

# Esta función, dado <instant> (Fecha y hora), retornará el bloque al que
# pertenece la hora proporcionada (Si esta está dentro de los límites del bloque)
# o el bloque más cercano. Es importante recalcar que encontrará el bloque más
# cercano dentro del día de la semana indicado. Por ejemplo; si nos encontramos
# el día Martes a las 23:00, nos retornaría el Martes 1-2 de la semana siguiente
# o un error (Véase el parámetro <strinctmode>).
# <strictmode: bool>: 
#   False: Se aproxima al bloque más cercano dentro del día de la semana indicado,
#    independiente de cuanto tiempo falte para ese bloque (Podrían ser desde
#    minutos, horas o incluso semanas).
#   True: Se aproxima al bloque más cercano dentro del día de la semana indicado
#    sólo si estamos dentro de los límites de la tolerancia; si falta mucho para
#    que comience el bloque o es demasiado tarde, lanzará un error.
def aproximateToShift(instant: datetime, strictmode = True) -> Shift:
    firstHour = instant.date()
    if (weekday := firstHour.weekday()) > 4:
        if strictmode:
            raise Exception(f'<instant> ({instant}) is not a weekday, so is not close enough to any block')
        firstHour += timedelta(days=7 - weekday)
    
    for block in parameters.Block:
        checkin = datetime.combine(firstHour, block.start)
        checkout = datetime.combine(firstHour, block.end)

        if strictmode:
            # Aproxima al siguiente bloque más cercano sólo si estamos dentro del
            # tiempo de tolerancia
            nextblockCondition = checkin - parameters.beforeStartTolerance < instant < checkin # <=
        else:
            # Aproxima directamente al bloque más cercano
            nextblockCondition = instant < checkin

        if (checkin <= instant <= checkout) or nextblockCondition:
            return Shift(firstHour, block)
    if strictmode:
        raise Exception(f'<instant> ({instant}) is not close enough to any block')
    
    return Shift(firstHour + timedelta(days=7), parameters.Block[0])
