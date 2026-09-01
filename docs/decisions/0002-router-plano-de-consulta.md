# ADR-0002 — Router plano de consulta junto al CRUD anidado

- **Estado**: aceptada
- **Fecha**: 2026-08-28
- **Relacionada**: [ADR-0001](0001-agregados-por-grupo.md)

## Contexto

Todos los endpoints de `transactions` cuelgan hoy de una cuenta:
`/api/v1/accounts/{account_id}/transactions`. Con esa forma no hay manera de responder a
"enséñame todos los movimientos del grupo de la categoría Comida" ni "busca *mercadona* en todas
mis cuentas": habría que pedir cuenta por cuenta y mezclar en el cliente, con el mismo problema de
consistencia temporal que motivó ADR-0001.

Al mismo tiempo, `ARCHITECTURE.md` §5.1 es tajante: *"un cambio incompatible en el contrato de un
endpoint existente requiere una nueva versión de prefijo, no una modificación in place"*. Mover o
reinterpretar `/accounts/{account_id}/transactions` no es una opción dentro de `/api/v1`.

Hay un tercer requisito que descarta atar esto al dashboard: la interfaz mostrará estadísticas
**también por cuenta**, no solo el agregado del grupo. Filtrar y agregar tienen que funcionar en
los dos ámbitos con el mismo contrato.

## Decisión

Se añade un **router plano de consulta**, `/api/v1/transactions`, con `group_id` obligatorio y
`account_id` opcional:

```
GET /api/v1/transactions?group_id=G                 → todas las cuentas del grupo
GET /api/v1/transactions?group_id=G&account_id=A    → solo la cuenta A
GET /api/v1/transactions/summary?group_id=G&...     → el agregado de ese mismo conjunto
```

`group_id` no es un filtro: es el **ámbito**, y es lo que resuelve la autorización vía
`RequireMembership`. `account_id` sí es un filtro más, al mismo nivel que `category_id`, `type`,
`date_from`/`date_to`, `q` o `uncategorized`.

De ahí se sigue la propiedad que buscábamos: **la vista de estadísticas de una cuenta y la del
dashboard son el mismo endpoint con un parámetro de diferencia.** El conjunto de filtros se define
una sola vez y lo comparten el listado y el agregado, de modo que un resumen describe exactamente
las mismas filas que devolvería el listado con esos mismos filtros.

El router anidado conserva **sin tocar** el CRUD de una transacción concreta (`POST`, `GET {id}`,
`PATCH`, `DELETE`) y su listado simple.

## Consecuencias

- Cero cambios incompatibles: nada de lo ya publicado cambia de forma ni de significado.
- Queda una **redundancia consciente**: `GET /accounts/{id}/transactions/` y
  `GET /transactions?group_id=G&account_id=id` devuelven lo mismo. Se acepta a cambio de no romper
  el contrato. Lo natural es retirar el listado anidado cuando exista un `/api/v2`; hasta entonces
  se documenta como el camino heredado y el plano como el recomendado.
- Autorizar por `group_id` y filtrar por `account_id` obliga a una validación nueva: que la cuenta
  pedida pertenezca al grupo sobre el que se tiene permiso. Sin ella, un miembro de un grupo podría
  leer movimientos de otro pasando un `account_id` ajeno. Es una comprobación de aplicación, no de
  base de datos, y va en el service.
- El nuevo router necesita registrarse aparte en `app/main.py`, porque un `APIRouter` solo admite
  un `prefix`.

## Alternativas descartadas

**Añadir los filtros al router anidado y nada más.** Añadir query params es aditivo y no rompería
§5.1, pero deja sin resolver el requisito de fondo: seguiría sin existir forma de listar
movimientos de todo el grupo filtrados. Buscar un texto en seis cuentas seguiría siendo seis
peticiones.

**Anidar bajo el grupo**: `/account-groups/{group_id}/transactions?account_id=`. Es la jerarquía
más ortodoxa, pero rompe la convención que ya siguen `accounts` y `categories`, que expresan el
grupo como query param (`GET /accounts/?group_id=`). Habría dos formas distintas de decir "grupo"
en la misma API, y `accounts.md` §4 ya razonó en su día por qué se eligió el query param.

**Sustituir el router anidado por el plano.** Es el diseño más limpio si se empezara de cero, y es
hacia donde debería ir una v2. Se descarta ahora por §5.1: sería un cambio incompatible en
endpoints ya publicados.
