# SPEC de dominio — accounts

## 1. Problema

Las cuentas financieras (banco, efectivo, tarjeta, inversión...) son donde vive el dinero real de un grupo — todo movimiento (`transactions`) y todo plan de pago futuro (`payment_plans`) ocurre siempre en el contexto de una cuenta concreta, nunca suelto. Sin este dominio no hay dónde registrar nada.

## 2. Relación con otros dominios

Depende de `account_groups` (toda cuenta pertenece a un `account_group`, nunca a un usuario directamente — ver `ARCHITECTURE.md` §6) y de `users` (`created_by`/`updated_by` referencian `User`). Es, a su vez, la base de la que dependen `payment_plans` y `transactions` — ninguno de los dos existe sin una cuenta a la que pertenecer.

Todos los endpoints exigen autenticación (`get_current_user`) y pertenencia al grupo de la cuenta sobre la que se opera. Los endpoints con `{account_id}` en la ruta (no `{group_id}`) resuelven esa pertenencia con `verify_account_access` (ver `ARCHITECTURE.md` §7.2): primero busca la cuenta, obtiene su `group_id`, y comprueba la pertenencia a partir de ahí — el cliente nunca necesita mandar el grupo por separado si ya conoce la cuenta.

## 3. Casos de uso

- Un miembro con rol `owner` o `admin` crea una cuenta nueva (banco, efectivo, tarjeta...) con un saldo inicial.
- Un miembro, sea cual sea su rol, consulta las cuentas de un grupo, o el detalle de una cuenta concreta.
- Un miembro con rol `owner` o `admin` actualiza los datos de una cuenta (nombre, tipo, color, icono) o la archiva.
- El saldo de una cuenta se mantiene siempre al día automáticamente a medida que se registran transacciones — nunca se escribe a mano desde la aplicación.

## 4. Endpoints

Prefijo de recurso: `/api/v1/accounts` — a propósito **no** anidado bajo `/account-groups/{group_id}/...`: mezclar el prefijo de otro dominio en la URL de `accounts` no refleja bien de qué API es cada recurso, aunque ambos endpoints de colección (`POST`, `GET`) sí necesitan `group_id` para autorizar. Se resuelve con `group_id` como **query param**, no como segmento de ruta ni en el body — así la dependencia de autorización (`RequireOwnerOrAdmin`/`RequireMembership`, ver `account_groups.md`) lo resuelve igual que ya hace con cualquier otra ruta, sin necesitar código de autorización propio de este dominio. Los endpoints con `{account_id}` en la ruta lo resuelven de otra forma (ver más abajo), porque ya no hace falta que el cliente indique el grupo por separado.

### `POST /api/v1/accounts?group_id={group_id}`

Requiere rol `owner` o `admin` en `group_id`.

- **Entrada** (body): `name`, `type` (opcional, por defecto `bank`), `opening_balance` (opcional, por defecto `0`), `currency` (opcional, por defecto `EUR`), `color` (opcional), `icon` (opcional). `group_id` no va en el body, va en la query string (ver más arriba).
- **Efecto**: crea la cuenta. `balance` nace igual a `opening_balance` — lo impone un trigger de base de datos (`trg_init_account_balance`), no la aplicación; el campo `balance` no se acepta como entrada porque no es un dato de origen, es derivado desde el primer instante.
- **Salida**: la cuenta creada.
- **Errores**: `403` si el usuario no pertenece a `group_id`, o pertenece pero con rol `member`. `409` si `currency` no coincide con la divisa ya establecida por otras cuentas activas del grupo (ver regla de negocio).

### `GET /api/v1/accounts?group_id={group_id}`

Requiere pertenencia al grupo, cualquier rol. `group_id` es obligatorio como query param — no existe un listado global de cuentas de todos los grupos a la vez, mismo principio que ya aplica a `transactions` en `ARCHITECTURE.md` §8.1: el acceso siempre ocurre en el contexto de un grupo o cuenta concreta.

- **Salida**: las cuentas del grupo (activas y archivadas — el cliente filtra por `is_active` si solo quiere ver las activas), envueltas en `{items: [...]}`, sin paginar.
- **Errores**: `403` si el usuario no pertenece a `group_id`.

### `GET /api/v1/accounts/{account_id}`

Requiere pertenencia al grupo de la cuenta.

- **Salida**: el detalle de la cuenta, incluido `balance`.
- **Errores**: `403` si el usuario no pertenece al grupo de la cuenta — nunca `404`, ni siquiera si la cuenta no existe (ver regla de negocio sobre este punto).

### `PATCH /api/v1/accounts/{account_id}`

Requiere rol `owner` o `admin` en el grupo de la cuenta. Actualización parcial (`ARCHITECTURE.md` §5.5).

- **Entrada**: `name`, `type`, `color`, `icon`, `is_active` — todos opcionales. `currency` y `opening_balance` **no** son editables aquí (ver regla de negocio).
- **Efecto**: `is_active = false` archiva la cuenta; no existe borrado físico en v1 (ver sección 6).
- **Errores**: `400` si no se incluye ningún campo (mismo criterio que `account_groups.md`). `403` si el usuario no pertenece al grupo de la cuenta, o pertenece pero con rol `member`.

## 5. Reglas de negocio

- **Gestionar cuentas es gobierno del grupo, no uso cotidiano**: crear, editar y archivar cuentas requiere rol `owner` o `admin`, el mismo corte que ya separa "administrar el grupo" de "participar en él" en `account_groups.md` §5. Un error aquí es difícil de deshacer (`currency`/`opening_balance` no editables, sin borrado físico) y afecta a todo el grupo, no solo a quien lo hace — a diferencia de una transacción, que es una anotación cotidiana, frecuente y de bajo riesgo. Por eso el SPEC de `transactions` (sin redactar todavía) está previsto que abra esa parte a cualquier `member`, aunque la gestión de las cuentas sobre las que se anota quede restringida aquí.
- **Divisa única por grupo** (resuelve la nota pendiente de `ARCHITECTURE.md` §6): todas las cuentas activas de un mismo `account_group` deben compartir `currency`. La primera cuenta que se crea en un grupo fija su divisa; cualquier cuenta posterior con una `currency` distinta devuelve `409`. Se valida a nivel de aplicación, no de base de datos (la columna no tiene ninguna restricción que lo imponga) — así el día que se decida soportar divisas mixtas por grupo, es un cambio de una sola validación, no una migración de esquema.
- `balance` nunca se escribe directamente desde la aplicación, ni en la creación ni en la actualización — nace de `opening_balance` (trigger `trg_init_account_balance`) y se mantiene con los triggers que definirá el SPEC de `transactions`. Por eso `opening_balance` tampoco es editable tras la creación: cambiarlo después desincronizaría `balance` de la suma real de sus movimientos, sin dejar rastro de por qué cambió.
- `currency` no es editable tras la creación: una cuenta con transacciones ya registradas en una divisa no puede cambiar de divisa sin invalidar todo su histórico. Si hace falta corregir una divisa mal elegida al crear la cuenta sin movimientos todavía, se archiva y se crea una nueva — no hay flujo de "corregir divisa" en v1.
- Igual que en `account_groups`, un error de autorización nunca se enmascara como recurso inexistente: no pertenecer al grupo de una cuenta da `403`, nunca `404`, tanto si la cuenta existe como si no (`ARCHITECTURE.md` §5.6).
- El borrado es lógico solo en el sentido de `is_active`, igual que `account_groups`: no hay columna `deleted_at` en `accounts` (a diferencia de `transactions`). Una cuenta archivada conserva su saldo e historial, y puede reactivarse con el mismo `PATCH`.

## 6. Fuera de alcance (v1)

- Borrado físico de una cuenta — solo archivado (`is_active = false`).
- Cambiar la `currency` o el `opening_balance` de una cuenta ya creada.
- Transferencias entre cuentas como concepto de este dominio — se resolverán como `transactions.type = 'transfer'`, en el SPEC de `transactions`.
- Múltiples divisas dentro de un mismo grupo.
- Saldo agregado por grupo (sumar el `balance` de todas las cuentas de un grupo) — mencionado como posible en `ARCHITECTURE.md` §8.1, pero ningún endpoint de este dominio lo calcula todavía.

## 7. Criterios de aceptación

- Crear una cuenta sin `opening_balance` la deja con `balance = 0`.
- Crear una cuenta con `opening_balance = 1050` (10,50€ en céntimos) la deja con `balance = 1050`.
- Crear una segunda cuenta en un grupo con una `currency` distinta a la primera cuenta activa del grupo devuelve `409`, sin crear la cuenta.
- Un `PATCH` sin ningún campo devuelve `400`, sin aplicar ningún cambio.
- Un `PATCH` con `currency` u `opening_balance` no los modifica (ver sección 6) — quedan fuera de los campos aceptados por el endpoint, no es un error silencioso, es que el schema de entrada no los admite.
- Un usuario autenticado pero sin pertenencia al grupo de la cuenta recibe `403` al operar sobre ella, tanto si la cuenta existe como si no.
- Un miembro con rol `member` que intenta crear, editar o archivar una cuenta recibe `403`; consultar cuentas sí le funciona con cualquier rol.
- Archivar una cuenta (`is_active = false`) no borra su `balance` ni su histórico; reactivarla con otro `PATCH` la deja consultable de nuevo.
