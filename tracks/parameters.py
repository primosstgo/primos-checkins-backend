from datetime import timedelta
from warnings import warn

days = 'lmxjv'

shifts = [
    ( "1-2" , ( 8, 15), ( 9, 25)),
    ( "3-4" , ( 9, 35), (10, 45)),
    ( "5-6" , (10, 55), (12,  5)),
    ( "7-8" , (12, 15), (13, 25)),
    ( "9-10", (14, 30), (15, 40)),
    ("11-12", (15, 50), (17,  0)),
    ("13-14", (17, 10), (18, 20)),
    ("15-16", (18, 30), (19, 40))
]

# TOLERANCIAS
# beforeStartTolerance: Cuanto tiempo antes de que comienze el turno se puede
#  iniciar el mismo. Establecer el valor de este parámetro por sobre el tiempo
#  de descanso entre bloques podría ocasionar bugs (no comprobado), puesto que
#   abre la posibilidad a comenzar un turno antes de que acabe el anterior.
beforeStartTolerance = timedelta(minutes=10)
# afterStartTolerance: Cuanto tiempo después de que comenzó el turno se puede
#  iniciar el mismo. Una buena idea es agregar 59 segundos extras, de esta forma
#  se concede el último minuto entero para iniciar el turno. Por ejemplo, si la
#  tolerancia es de 10 minutos, esta medida permite a los primos iniciar su turno
#  entre el minuto 0 y el minuto 10 ([0, 10]), de modo que el turno se cerrará
#  apenas comience el minuto 11. De no agregar estos 59 segundos el turno se
#  cerraría apenas comiencie el minuto 10 ([0, 10[).
afterStartTolerance = beforeStartTolerance + timedelta(seconds=59)
# afterEndTolerance: Cuanto tiempo se concede al primo para cerrar su turno,
#  una vez terminada la hora, sin que se considere sospechoso.
afterEndTolerance = beforeStartTolerance

# Esta función se asegura de que los parámetros tengan sentido
def checks():
    badBlocks = []
    for i in range(len(shifts)):
        if not (shifts[i][1] < shifts[i][2]):
            badBlocks.append(Exception(f'El bloque {shifts[i][0]} ({shifts[i][1][0]}:{shifts[i][1][1]} - {shifts[i][2][0]}:{shifts[i][2][1]}) termina antes de comenzar'))
    for i in range(len(shifts) - 1):
        if not (shifts[i][2] < shifts[i + 1][1]):
            badBlocks.append(Exception(f'El bloque {shifts[i + 1][0]} comienza antes de que termine el bloque anterior'))
    if badBlocks:
        raise Exception(badBlocks)
    
    minDuration = timedelta(*(0,)*4, *shifts[0][2][::-1]) - timedelta(*(0,)*4, *shifts[0][1][::-1])
    for shift in shifts[1:]:
        duration = timedelta(*(0,)*4, *shift[2][::-1]) - timedelta(*(0,)*4, *shift[1][::-1])
        if duration < minDuration:
            minDuration = duration
    if afterStartTolerance >= minDuration:
        raise Exception(f'La tolerancia <afterStartTolerance> ({str(afterStartTolerance)}) es mayor a la duración del bloque más corto ({minDuration})')

    minRest = timedelta(hours=shifts[1][1][0], minutes=shifts[1][1][1]) - timedelta(hours=shifts[0][2][0], minutes=shifts[0][2][1])
    for i in range(len(shifts) - 2):
        start, end = shifts[i + 1][2], shifts[i + 2][1]
        if (rest := timedelta(hours=end[0] - start[0], minutes=end[1] - start[1])) < minRest:
            minRest = rest
    if beforeStartTolerance > minRest:
        warn(f'El tiempo de tolerancia <beforeStartTolerance> ({str(beforeStartTolerance)}) es mayor al descanso más pequeño ({minRest})')
    if afterEndTolerance > minRest:
        warn(f'El tiempo de tolerancia <afterEndTolerance> ({str(afterEndTolerance)}) es mayor al descanso más pequeño ({minRest})')
checks()
