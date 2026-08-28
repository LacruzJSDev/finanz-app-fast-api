# ADR-0003 — El ancla de cobro se deriva, sin columna nueva

- **Estado**: aceptada
- **Fecha**: 2026-08-28
- **Relacionada**: [ADR-0001](0001-agregados-por-grupo.md)

## Contexto

La pantalla principal del dashboard se organiza entera alrededor de una idea: **cuánto queda hasta
el próximo cobro**. De ahí salen "hasta el día 5", "9 días restantes", el saldo real (disponible
menos los gastos fijos que aún tienen que salir), el gasto diario seguro (saldo real entre días
restantes) y el horizonte de la proyección.

Todos esos cálculos necesitan una fecha de referencia: cuándo entra el próximo ingreso periódico.

El dominio `payment_plans` ya sabe modelar una nómina: un plan con `type='income'`,
`is_recurring=true`, `frequency_unit='month'` y `next_due_date` en el día que toca. El dato existe.
Lo que no existe es forma de saber **cuál** de todos los planes de un grupo es el que define el
ciclo.

## Decisión

No se añade ninguna columna. El ancla se deriva por convención: el `payment_plan` activo del grupo
con `type='income'` e `is_recurring=true` que tenga el `next_due_date` más próximo. Se desempata
por `amount` descendente, porque si dos ingresos recurrentes caen el mismo día la nómina es casi
siempre el mayor.

Su `next_due_date` **es** la fecha de cobro, y su `amount` es lo que entra ese día. No hace falta
aritmética de calendario en ninguna parte: el cron diario (`app/payment_plans/run_due.py`) ya
avanza `next_due_date` al materializar el plan, incluido el ajuste de fin de mes con
`calendar.monthrange`.

Si un grupo no tiene ningún plan que cumpla la convención, los endpoints **no fallan**: devuelven
`payday`, `daily_safe_spend` y `projection` a `null`, y siguen sirviendo patrimonio, disponible y
gastado hoy. Un dashboard que responde 409 porque falta configurar algo es un dashboard hostil.

## Consecuencias

- **El ancla se puede secuestrar.** Cualquier ingreso recurrente con fecha más próxima que la
  nómina —un alquiler que se cobra el día 2, una devolución periódica— pasa a definir el ciclo, y
  el usuario no tiene forma de corregirlo salvo archivando ese plan. Es el precio explícito de no
  añadir columna, y queda documentado como limitación conocida en `payment_plans.md` §6.
- Cuando eso moleste en uso real, la salida está acotada y es pequeña: una columna
  `payment_plans.is_payday` con un `CHECK` de "solo income recurrente" y un trigger de unicidad por
  grupo (el grupo no es columna de esa tabla, se llega por `accounts`, así que un índice único no
  basta). Sería un ADR nuevo que sustituya a este, no un rediseño.
- Cero migraciones. Combinado con [ADR-0004](0004-cuentas-gastables-por-tipo.md), toda la pantalla
  del dashboard sale del esquema actual sin tocar la base de datos.
- El plan que resulta ser el ancla debe **excluirse de los gastos fijos pendientes**, y se excluye
  por `id`, no por heurística: es un ingreso, y el filtro de pendientes ya se queda solo con
  `type='expense'`.

## Alternativas descartadas

**Columna `payment_plans.is_payday`.** Técnicamente la mejor: la nómina es un plan, así que fecha,
importe, cuenta y periodicidad ya están ahí, y marcarla explícitamente elimina toda ambigüedad. Se
descartó para esta iteración por coste: columna, `CHECK`, índice parcial, trigger de unicidad por
grupo, campos nuevos en dos schemas y validación en el service, todo para un dato que en la
práctica casi siempre se puede adivinar. Queda como la salida natural si la convención falla.

**Columna `account_groups.payday_day_of_month`.** Lo más barato de todo, un entero con un `CHECK`
entre 1 y 31. Se descarta porque duplica un dato que ya vive en `payment_plans` y se desincroniza
en silencio en cuanto cambia la nómina, obliga a reimplementar el ajuste de los días 29-31 que el
cron ya resuelve, y no sabe ni cuánto se cobra ni en qué cuenta — con lo que la proyección no
podría dibujar la entrada del día de cobro.
