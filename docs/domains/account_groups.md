# SPEC de dominio — account_groups

## 1. Problema

Las cuentas, categorías y transacciones no pertenecen a un usuario individual, sino a un espacio compartido — un grupo puede representar a una persona sola o a varias compartiendo finanzas (pareja, piso compartido...). Sin esa unidad de agrupación, cualquier funcionalidad multiusuario obligaría a duplicar datos por cada miembro.

## 2. Relación con otros dominios

Depende de `users` (los miembros y quien invita/acepta referencian `User`, nunca al revés). Es, a su vez, la base de la que dependen `accounts`, `categories`, `payment_plans` y `transactions` — ninguno de esos dominios existe sin un `account_group` al que pertenecer (ver `ARCHITECTURE.md` §6).

Todos los endpoints exigen autenticación (`get_current_user`) y, salvo la creación de un grupo, pertenencia al grupo sobre el que se opera (`verify_group_membership`, ver `ARCHITECTURE.md` §7.2).

## 3. Casos de uso

- Un usuario autenticado crea un grupo nuevo y pasa a ser su `owner`.
- Un miembro con rol `owner` o `admin` invita a otro usuario al grupo, generando un código.
- Un usuario autenticado consulta una invitación por su código para ver quién le invitó, a qué grupo y con qué rol, antes de decidir si la acepta.
- Un usuario autenticado acepta una invitación mediante su código y pasa a ser miembro con el rol indicado en la invitación.
- Un miembro consulta los grupos a los que pertenece y los miembros de un grupo concreto.
- Un miembro con rol suficiente actualiza los datos del grupo (nombre, color, icono) o lo archiva.
- Un `owner` cambia el rol de otro miembro.
- Un miembro abandona un grupo; un `owner`/`admin` elimina a otro miembro.

## 4. Endpoints

Prefijo de recurso: `/api/v1/account-groups` (kebab-case en la URL — no hay precedente todavía en el proyecto para nombres de recurso compuestos; se fija aquí como convención para el resto de dominios).

### `POST /api/v1/account-groups`

- **Entrada**: `name`, `color` (opcional), `icon` (opcional).
- **Efecto**: crea el grupo y, en la misma operación, una fila en `account_group_members` con `role = 'owner'` para quien lo crea. Un grupo nunca existe sin al menos un `owner`.
- **Salida**: el grupo creado.

### `GET /api/v1/account-groups`

- **Salida**: los grupos a los que pertenece el usuario autenticado, envueltos en `{items: [...]}` (ver `ARCHITECTURE.md` §5.4) — sin paginar, acotado de forma natural por cuántos grupos puede tener una persona.

### `PATCH /api/v1/account-groups/{group_id}`

Requiere rol `owner` o `admin` en el grupo. Actualización parcial (§5.5).

- **Entrada**: `name`, `color`, `icon`, `is_active` — todos opcionales.
- **Efecto**: `is_active = false` es la forma de archivar un grupo; no existe borrado físico en v1 (ver sección 6).
- **Errores**: `403` si el usuario es miembro del grupo pero no tiene rol `owner`/`admin`. `403` (no `404`) si no es miembro en absoluto — un error de autorización nunca se enmascara como recurso inexistente (`ARCHITECTURE.md` §5.6).

### `GET /api/v1/account-groups/{group_id}/members`

Requiere pertenencia al grupo, cualquier rol.

- **Salida**: los miembros del grupo, envueltos en `{items: [...]}`, sin paginar.

### `PATCH /api/v1/account-groups/{group_id}/members/{user_id}`

Requiere rol `owner`.

- **Entrada**: `role`.
- **Efecto**: cambia el rol del miembro indicado. No hay un endpoint separado de "transferir propiedad": un grupo puede tener más de un `owner` simultáneamente (el esquema no lo impide), así que promover a un segundo miembro a `owner` ya resuelve ese caso.
- **Errores**: `409` si la operación dejaría al grupo sin ningún `owner` (ver regla de negocio).

### `DELETE /api/v1/account-groups/{group_id}/members/{user_id}`

Requiere ser el propio `user_id` (abandonar el grupo) o rol `owner`/`admin` sobre otro miembro (expulsar). Un `admin` no puede expulsar a un `owner`.

- **Errores**: `409` si `user_id` es el único `owner` del grupo y quedarían otros miembros (ver regla de negocio).

### `POST /api/v1/account-groups/{group_id}/invitations`

Requiere rol `owner` o `admin`.

- **Entrada**: `role` (el rol con el que se unirá quien acepte).
- **Efecto**: crea una fila en `invitations` con un `code` aleatorio y `expires_at` (ver sección 5 para la duración).
- **Salida**: la invitación, incluido `code` — es responsabilidad del cliente comunicárselo a la persona invitada, fuera del alcance de este dominio (no hay envío de email en v1, ver sección 6).

### `GET /api/v1/account-groups/invitations/{code}`

Requiere autenticación, no pertenencia previa al grupo.

- **Salida**: la invitación — grupo, quién invitó, rol ofrecido y `status`. Permite al cliente mostrar "X te ha invitado a Y" antes de que el usuario decida aceptar, y de paso resolver el `group_id` que necesita para llamar al endpoint de aceptar (ver más abajo), ya que quien recibe el enlace de invitación solo tiene el `code`.
- **Efecto**: si `expires_at` ya pasó, o si el usuario que invitó ha borrado su cuenta desde entonces (`invited_by` es `NULL` — ver sección 5 sobre `ON DELETE SET NULL`), la invitación se marca `expired` en este mismo momento, de forma perezosa (no hay ningún proceso en segundo plano que recorra invitaciones caducadas). `invited_by` no borra la fila (se preserva el histórico), pero deja la invitación tan inutilizable como si hubiera caducado por tiempo — no tiene sentido unirse a un grupo por una invitación de alguien que ya no está; el invitado tiene que pedir un código nuevo a otro miembro.
- **Errores**: `404` si el código no existe. Una invitación `accepted` o expirada (por tiempo o por invitador borrado) **no** es un error aquí — es una simple consulta, no un cambio de estado, así que se devuelve igual que cualquier otra, con su `status` real en el cuerpo (`invited_by: null` si el invitador ya no existe); es responsabilidad del cliente decidir qué mostrar (por ejemplo, "esta invitación ya expiró") en vez de dejar que lo intente aceptar.

### `POST /api/v1/account-groups/{group_id}/invitations/{code}/accept`

Requiere autenticación, no pertenencia previa al grupo.

- **Efecto**: valida que la invitación exista, esté `pending` y no haya expirado; crea la fila en `account_group_members` con el rol de la invitación; marca la invitación como `accepted`, con `accepted_by` y `accepted_at`.
- **Errores**: `404` si el código no existe. `409` si ya está `accepted` o expirada (transición de estado inválida, no un problema de autorización — por eso `409` y no `403`/`401`). A diferencia del resto de endpoints anidados bajo `{group_id}`, aquí el `code` por sí solo ya identifica la invitación sin ambigüedad — `group_id` en la ruta es solo por consistencia con el resto del dominio, el cliente lo obtiene primero con el `GET` de arriba.

## 5. Reglas de negocio

- Un grupo siempre tiene al menos un `owner` mientras tenga algún miembro. El único `owner` de un grupo con otros miembros no puede abandonarlo ni ser eliminado, ni puede degradarse su propio rol, sin que antes se promueva a otro miembro a `owner`. Si es además el único miembro del grupo, sí puede abandonarlo — el grupo queda sin miembros, no se borra ni se archiva automáticamente. Esto resuelve la dependencia que `docs/domains/users.md` §6 dejaba abierta sobre la baja de un usuario que sea único `owner` de un grupo con más miembros: ese caso debe bloquearse aquí, en `account_groups`, antes de que `users` pueda implementar `DELETE /me`.
- Los roles son jerárquicos para las acciones de gestión: `owner` puede todo lo que puede `admin`; `admin` puede invitar y expulsar `member`, pero no a otro `admin` ni a un `owner`. Cualquier miembro, sea cual sea su rol, puede ver los datos del grupo y abandonar voluntariamente (salvo la restricción de único `owner`).
- Duración de una invitación: 7 días desde su creación. El código no se reutiliza tras aceptarse ni tras expirar; una invitación caducada requiere crear una nueva.
- La divisa única por grupo (`accounts.currency`, no `account_groups.currency`) se valida a nivel de aplicación, no de base de datos — ver `ARCHITECTURE.md` §6. La validación concreta se define en el SPEC de `accounts`, todavía sin redactar; este dominio no la implementa.
- El borrado es lógico solo en el sentido de `is_active`: no hay una columna `deleted_at` en `account_groups` (a diferencia de `transactions`). Un grupo archivado conserva todos sus datos y puede reactivarse con el mismo `PATCH`.

## 6. Fuera de alcance (v1)

- Envío de la invitación por email — el `code` se genera y se devuelve al cliente, pero comunicárselo al invitado es responsabilidad del frontend (por ejemplo, compartiendo un enlace).
- Rechazar explícitamente una invitación (`status = 'expired'` solo se alcanza por el paso del tiempo, no por una acción del invitado).
- Revocar o listar invitaciones pendientes ya creadas.
- Roles personalizados más allá de `owner`/`admin`/`member`.
- Borrado físico de un grupo — solo archivado (`is_active = false`).
- Transferencia de propiedad como operación dedicada (se resuelve con `PATCH` de rol, ver sección 4).

## 7. Criterios de aceptación

- Crear un grupo crea también, en la misma operación, la fila de `account_group_members` con `role = 'owner'` para quien lo creó.
- Consultar una invitación con un código inexistente devuelve `404`; con un código válido pero ya `accepted` o expirado, devuelve `200` con el `status` real, no un error.
- Consultar una invitación `pending` cuyo `invited_by` ha borrado su cuenta la marca `expired` en ese momento y la devuelve con `invited_by: null`, sin dar ningún error.
- Aceptar una invitación con un código inexistente devuelve `404`.
- Aceptar una invitación ya aceptada, o una con `expires_at` en el pasado, devuelve `409`, sin crear una fila de pertenencia.
- Intentar que el único `owner` de un grupo con otros miembros lo abandone, sea eliminado, o cambie su propio rol, devuelve `409`, sin aplicar el cambio.
- El único `owner` y único miembro de un grupo sí puede abandonarlo.
- Un usuario autenticado pero sin pertenencia al grupo recibe `403` al operar sobre él, nunca `404`.
- Un `admin` que intenta expulsar a un `owner` recibe `403`.
