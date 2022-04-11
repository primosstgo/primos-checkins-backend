from datetime import timedelta


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

# OJO: Establecer el valor de este parámetro por sobre el tiempo de descanso
#      entre bloques podría ocasionar bugs, puesto que abre la posibilidad a
#      comenzar un turno antes de que acabe el anterior.
#      En el futuro quizás convendría separar la tolerancia en superior
#      (Tolerancia a iniciar el turno antes de que el bloque comience) y
#      inferior (Tolerancia a finalizar un turno después de que el bloque
#      terminó); así la tolerancia inferior no tendría esta limitación.
tolerance = timedelta(minutes=10)