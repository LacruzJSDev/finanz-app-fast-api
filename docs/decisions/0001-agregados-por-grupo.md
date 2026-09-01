# ADR-0001 — Los agregados por grupo son una excepción explícita al acceso por cuenta

- **Estado**: aceptada
- **Fecha**: 2026-08-28
- **Sustituye**: la redacción original de `ARCHITECTURE.md` §8.1, y los puntos de "fuera de
  alcance" sobre saldo agregado de `accounts.md` §6 y `transactions.md` §6

## Contexto

`ARCHITECTURE.md` §8.1 decía, literalmente, que el acceso a transacciones se realiza siempre en el
contexto de una cuenta específica, *"nunca agregando todas las cuentas de un grupo en una sola
consulta"*, y que el saldo agregado de un grupo se obtiene sumando los saldos ya derivados de sus
cuentas. Coherente con eso, el saldo agregado por grupo quedó explícitamente fuera de alcance en
los SPEC de `accounts` y `transactions`.

Esa regla se escribió antes de que existiera ninguna pantalla de estadísticas. Al diseñar el
dashboard y las vistas de estadísticas por cuenta aparecen preguntas que son **intrínsecamente de
grupo**: cuánto patrimonio hay en total, cuánto se ha gastado hoy, cómo se reparte el gasto del mes
entre categorías. Responderlas bajo la regla anterior obliga al cliente a pedir N veces (una por
cuenta) y sumar a mano.

Eso tiene dos problemas, y el segundo es el grave:

1. Son N peticiones, N sesiones de base de datos y N pasadas de autorización para pintar una
   pantalla.
2. **Cada petición ve un instante distinto de la base de datos.** Entre la primera y la última
   puede cruzarse la medianoche, o el cron diario de `payment_plans` que avanza `next_due_date`, y
   la pantalla acaba mezclando cifras de dos estados del mundo. Además, el cliente termina
   reimplementando aritmética financiera que pertenece al servidor.

## Decisión

El acceso **al detalle** de una transacción (crear, leer una, editar, borrar) sigue colgando de una
cuenta concreta. Los **agregados** son la excepción explícita: se calculan en el servidor, en una
sola consulta, con el grupo como ámbito.

Reglas que todo endpoint agregado cumple:

- Va **siempre** bajo `group_id`, nunca sin ámbito. `group_id` es además lo que resuelve la
  autorización (`RequireMembership`).
- Vive en **el dominio dueño del dato**, no en un dominio `dashboard` transversal: el saldo
  agregado en `accounts`, el desglose por categoría en `transactions`, los vencimientos en
  `payment_plans`. Un dominio `dashboard` acabaría siendo un cajón de sastre que conoce el esquema
  de todos los demás y se rompe cada vez que uno cambia.
- `transactions` no tiene columna `group_id`: todo agregado llega al grupo con
  `JOIN accounts ON accounts.id = transactions.account_id`.
- Todo agregado excluye `deleted_at IS NOT NULL` y, cuando reparte entre ingreso y gasto, excluye
  también `type = 'transfer'` — un movimiento interno no es ninguna de las dos cosas: sumaría cero
  al total pero ensuciaría el desglose con una fila por cada cuenta implicada.

`GET /account-groups/{group_id}/overview` compone varios de estos agregados en una sola respuesta,
reutilizando los services de los demás dominios, para que toda una pantalla se calcule contra el
mismo instante. No es un dominio nuevo: es un endpoint más de `account_groups`, igual que
`/account-groups/{group_id}/members`.

## Consecuencias

- Aparecen las primeras consultas agregadas del proyecto. Hasta ahora no había ni un `func.sum` ni
  un `group_by` en todo el repositorio; el único agregado era el `func.count()` que pagina
  transacciones. No hay precedente interno que copiar, así que las convenciones (castear el
  `Decimal` que devuelve `SUM` sobre `BIGINT`, `coalesce` a cero, `FILTER` para varias sumas en un
  escaneo) se fijan en `ARCHITECTURE.md` §8.3.
- Los tests unitarios actuales, basados en `MagicMock`, **no pueden cubrir estas consultas**: sin
  base de datos de test el SQL nunca se ejecuta. Se compensa con criterios de aceptación manuales
  en cada SPEC, en vez de fingir una cobertura que no existe.
- La aritmética financiera derivada (saldo real, gasto diario seguro, proyección) queda en el
  servidor, donde puede testearse, en lugar de repetirse en cada cliente.

## Alternativas descartadas

**Mantener la regla y sumar en el cliente.** Es la que había. Se descarta por el problema de
consistencia temporal descrito arriba: no es una cuestión de rendimiento, es que la pantalla puede
mostrar cifras incoherentes entre sí, y ningún cliente puede arreglarlo por su cuenta.

**Un dominio `dashboard` transversal** que concentre todos los agregados. Se descarta porque cada
agregado pertenece conceptualmente a un dominio existente y necesita sus modelos; un dominio
aparte tendría que conocer el esquema de `accounts`, `transactions`, `categories` y
`payment_plans` a la vez, y quedaría acoplado a los cuatro. Además, las estadísticas no son
exclusivas del dashboard: la interfaz también las mostrará por cuenta, así que atarlas a una
pantalla concreta habría sido un error de nombre y de alcance.

**Vistas materializadas o una tabla de resumen precalculada.** Se descarta por prematuro:
`ARCHITECTURE.md` §9 fija un supuesto de volumen bajo (uso personal o de grupo reducido), donde un
`SUM` sobre unos miles de filas es instantáneo. Introducir precálculo traería el problema de
invalidación sin resolver ningún problema real todavía.
