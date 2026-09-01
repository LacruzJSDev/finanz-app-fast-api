# ADR-0006 — Revocar una invitación la borra, no la marca

- **Estado**: aceptada
- **Fecha**: 2026-08-29
- **Sustituye**: el punto de `account_groups.md` §6 que dejaba fuera de alcance "revocar o listar invitaciones pendientes ya creadas"

## Contexto

El frontend necesita una pantalla de gestión de invitaciones: ver las que hay en un grupo y poder
cortar una que se creó por error o que ya no interesa. Eso exige dos endpoints que no existían y
que el SPEC declaraba explícitamente fuera de alcance.

Listar no tiene discusión. Revocar sí: hay que decidir qué significa exactamente "revocada" en el
modelo, y la tabla `invitations` no ayuda a decidirlo sola. Por un lado, su diseño está pensado
como registro histórico — el comentario de `schema-reference.sql` justifica los `ON DELETE SET
NULL` de `invited_by`/`accepted_by` precisamente para que "el historial de invitaciones sobreviva"
aunque esos usuarios borren su cuenta. Por otro, `ARCHITECTURE.md` §8.2 fija que el borrado físico
es la convención por defecto y que el lógico es una excepción justificada, hoy solo en
`transactions`.

## Decisión

`DELETE /api/v1/account-groups/{group_id}/invitations/{invitation_id}` **borra la fila**.

Se puede revocar cualquier invitación que **nadie haya usado**: una `pending` o una `expired`. Una
`expired` se borra igual porque no aporta nada y solo ensucia la pantalla de gestión.

Lo único intocable es una `accepted`, que devuelve `409`: su fila es el registro de que alguien
entró al grupo, y borrarla reescribiría un hecho. Para deshacer eso ya existe el endpoint de
expulsar miembros, que es lo que corresponde.

La tensión con el carácter histórico de la tabla se resuelve observando **qué** se borra: una
invitación pendiente y revocada es una que nadie llegó a usar. No hay ningún hecho que preservar,
solo una intención que se retiró. El historial que la tabla protege es el de las invitaciones
*aceptadas*, y esas siguen siendo intocables.

## Consecuencias

- Sin migración y sin columnas nuevas. `status_enum` se queda como está.
- **Se pierde el rastro de la revocación**: quién la revocó y cuándo. No queda registrado en
  ninguna parte. Es el precio explícito de esta decisión.
- El `code` de una invitación borrada queda libre. En la práctica da igual: se generan
  aleatoriamente y no se reutilizan (`account_groups.md` §5).
- El listado aplica la misma caducidad perezosa que el `GET` por código, así que un `DELETE` sobre
  algo que la pantalla mostraba como `pending` no puede encontrárselo ya `expired` por sorpresa —
  y aunque así fuera, borrar una expirada también está permitido.

## Alternativas descartadas

**Un valor `revoked` en `status_enum`.** Conserva el rastro y distingue "la corté yo" de "caducó
sola", que es información real. Se descarta por coste desproporcionado para lo que aporta: en
Postgres, `ALTER TYPE ... ADD VALUE` tiene restricciones dentro del bloque transaccional en el que
Alembic ejecuta sus migraciones, y además no es reversible — no se puede quitar un valor de un
enum, así que el `downgrade` tendría que recrear el tipo entero y reescribir la columna. Todo eso
para un dato que hoy nadie consulta, porque el proyecto no tiene log de auditoría en ningún
dominio: saber *quién* revocó seguiría sin estar disponible.

**Reutilizar `expired`.** Cero coste, pero el dato mentiría: nadie podría distinguir una
invitación que caducó sola de una que alguien cortó a propósito. Un estado que significa dos cosas
distintas es peor que no tener el estado.
