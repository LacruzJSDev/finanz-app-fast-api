# SPEC de dominio — account_groups

## 1. Problema

Las cuentas, categorías y transacciones no pertenecen a un usuario individual, sino a un espacio compartido — un grupo puede representar a una persona sola o a varias compartiendo finanzas (pareja, piso compartido...). Sin esa unidad de agrupación, cualquier funcionalidad multiusuario obligaría a duplicar datos por cada miembro.

## 2. Relación con otros dominios

Depende de `users` (los miembros y quien invita/acepta referencian `User`, nunca al revés). Es, a su vez, la base de la que dependen `accounts`, `categories`, `payment_plans` y `transactions` — ninguno de esos dominios existe sin un `account_group` al que pertenecer (ver `ARCHITECTURE.md` §6).

Todos los endpoints exigen autenticación (`get_current_user`) y, salvo la creación de un grupo, pertenencia al grupo sobre el que se opera (`verify_group_membership`, ver `ARCHITECTURE.md` §7.2).

## 3. Casos de uso

- Un usuario autenticado crea un grupo nuevo y pasa a ser su `owner`.
- Un miembro con rol `owner` o `admin` invita a otro usuario al grupo, generando un código.
- Un miembro con rol `owner` o `admin` consulta las invitaciones de su grupo para saber a quién se ha invitado y en qué estado está cada invitación.
- Un miembro con rol `owner` o `admin` revoca una invitación que creó por error o que ya no interesa, antes de que nadie la acepte.
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
- **`members` viene completo, incluido quien consulta.** No es un detalle de eficiencia: es el único sitio de esta respuesta donde viaja un `role`, así que excluirse a uno mismo deja al cliente sin saber qué puede hacer en cada grupo — si mostrar la gestión de roles, si puede invitar, si puede archivar. Además, cualquier recuento derivado de la lista saldría corto por uno. Si algún día el tamaño de la respuesta llegara a importar, la salida es exponer el rol propio como campo escalar del grupo, nunca recortar `members`.

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

### `GET /api/v1/account-groups/{group_id}/invitations`

Requiere rol `owner` o `admin`. Es la pantalla de gestión: quién ha sido invitado y en qué estado está cada invitación.

- **Salida**: todas las invitaciones del grupo —`pending`, `accepted` y `expired`— envueltas en `{items: [...]}`, sin paginar, ordenadas por `created_at` descendente. El volumen esperado por grupo es pequeño (`ARCHITECTURE.md` §5.4). Se devuelven todas y no solo las pendientes para que el cliente pueda filtrar sin necesitar un segundo endpoint más adelante.
- **Efecto**: aplica la misma caducidad perezosa que el `GET` por código (ver sección 5): las invitaciones `pending` cuyo `expires_at` ya pasó, o cuyo `invited_by` ha borrado su cuenta, pasan a `expired` en este mismo momento. Sí, es un `GET` que escribe; la alternativa era tener dos reglas distintas de caducidad y que acabaran divergiendo.
- **`code` se devuelve en cada fila**: quien puede ver esta lista es quien puede crear invitaciones, así que no hay nada que ocultarle — y le permite recuperar y reenviar un enlace que se perdió, sin tener que crear otra invitación.
- **Errores**: `403` si el usuario no pertenece al grupo, o pertenece con rol `member`.

### `DELETE /api/v1/account-groups/{group_id}/invitations/{invitation_id}`

Requiere rol `owner` o `admin`. Revoca una invitación que aún no se ha usado.

- **Efecto**: **borra la fila** ([ADR-0006](../decisions/0006-revocar-invitaciones-borrado-fisico.md)). No hay borrado lógico ni estado `revoked`.
- **Salida**: `204 No Content`.
- **Errores**: `403` si el usuario no pertenece al grupo, o pertenece con rol `member`. `404` si `invitation_id` no existe o pertenece a otro grupo — mismo criterio que el endpoint de aceptar, no se revela que la invitación es válida en otro sitio; revocar dos veces devuelve `404` la segunda. `409` si la invitación está `accepted` (ver sección 5).

### `GET /api/v1/account-groups/invitations/{code}`

Requiere autenticación, no pertenencia previa al grupo.

- **Salida**: la invitación con **el grupo completo embebido** (`group`: nombre, color, icono…), además de quién invitó, el rol ofrecido y el `status`. Permite al cliente mostrar "X te ha invitado a Y" antes de que el usuario decida aceptar, y de paso resolver el `group_id` que necesita para llamar al endpoint de aceptar (ver más abajo), ya que quien recibe el enlace de invitación solo tiene el `code`.
- **Es el único endpoint que embebe el grupo**, y por eso usa un schema propio en vez del `InvitationRead` que devuelven los demás. La razón es que aquí, y solo aquí, quien consulta **no pertenece al grupo**: no puede pedirlo por separado a `GET /account-groups`, que exige pertenencia. En el listado de gestión, en cambio, el grupo ya se conoce — va en la propia URL —, así que embeberlo en cada fila sería repetir el mismo objeto N veces sin que nadie lo necesite.
- **Efecto**: si `expires_at` ya pasó, o si el usuario que invitó ha borrado su cuenta desde entonces (`invited_by` es `NULL` — ver sección 5 sobre `ON DELETE SET NULL`), la invitación se marca `expired` en este mismo momento, de forma perezosa (no hay ningún proceso en segundo plano que recorra invitaciones caducadas). `invited_by` no borra la fila (se preserva el histórico), pero deja la invitación tan inutilizable como si hubiera caducado por tiempo — no tiene sentido unirse a un grupo por una invitación de alguien que ya no está; el invitado tiene que pedir un código nuevo a otro miembro.
- **Errores**: `404` si el código no existe. Una invitación `accepted` o expirada (por tiempo o por invitador borrado) **no** es un error aquí — es una simple consulta, no un cambio de estado, así que se devuelve igual que cualquier otra, con su `status` real en el cuerpo (`invited_by: null` si el invitador ya no existe); es responsabilidad del cliente decidir qué mostrar (por ejemplo, "esta invitación ya expiró") en vez de dejar que lo intente aceptar.

### `POST /api/v1/account-groups/{group_id}/invitations/{invitation_id}/accept`

Requiere autenticación, no pertenencia previa al grupo.

Identifica la invitación por `invitation_id`, no por `code` — el cliente ya lo tiene tras el `GET` anterior, así que no hace falta mandar el `code` una segunda vez. No es una cuestión de seguridad (los dos son igual de difíciles de adivinar), es evitar repetir el mismo dato dos veces en el mismo flujo.

- **Efecto**: valida que la invitación exista para ese `group_id`, esté `pending`, no haya expirado y su `invited_by` siga existiendo (ver regla de negocio sobre invitador borrado); crea la fila en `account_group_members` con el rol de la invitación; marca la invitación como `accepted`, con `accepted_by` y `accepted_at`.
- **Errores**: `404` si `invitation_id` no existe, **o si existe pero pertenece a un grupo distinto del `group_id` de la ruta** — se trata igual que "no existe", nunca se revela que la invitación es válida para otro grupo. `409` si ya está `accepted`, si ha expirado (por tiempo o porque su `invited_by` ya no existe), o si quien acepta ya es miembro del grupo — todos son transiciones de estado inválidas, no problemas de autorización, por eso `409` y no `403`/`401`.

### `GET /api/v1/account-groups/{group_id}/overview`

Requiere pertenencia al grupo, cualquier rol. **Endpoint de composición** (`ARCHITECTURE.md` §8.3): reúne agregados de `accounts`, `transactions` y `payment_plans` en una sola respuesta, reutilizando los services de esos dominios sin reimplementar sus consultas.

Existe por corrección, no por rendimiento: todos sus bloques tienen que calcularse contra **el mismo `today` y el mismo ancla de cobro**. Pedidos por separado, dos de ellos podrían cruzar la medianoche, o cruzarse con el cron diario que avanza `next_due_date`, y la respuesta mostraría "9 días restantes" junto a una proyección que termina el mes siguiente.

- **Entrada**: nada más que el `group_id` de la ruta.
- **Salida**: `GroupOverviewRead`, con estos bloques:
  - `net_worth`, `available`, `account_count` — de `accounts` (`GET /accounts/balance`).
  - `spent_today`, `transaction_count_today` — de `transactions` (`GET /transactions/daily`).
  - `payday` — la fecha del ancla de cobro y su importe, o `null` (ver `payment_plans.md` §5).
  - `pending_fixed_expenses` — los gastos fijos que aún tienen que salir antes del cobro, y su total.
  - `real_balance` — `available` menos ese total.
  - `days_remaining`, `daily_safe_spend` — días hasta el cobro y cuánto se puede gastar al día sin quedarse corto.
  - `projection` — la curva día a día del saldo desde hoy hasta el cobro, restando cada gasto fijo en su fecha.
- **Sin ancla de cobro**, `payday`, `days_remaining`, `daily_safe_spend` y `projection` van a `null`, pero `net_worth`, `available` y el gasto de hoy **sí se devuelven**. Un resumen que responde `409` porque falta configurar algo es inútil justo cuando más falta hace.
- No va envuelto en `{items}`: no es una colección (`ARCHITECTURE.md` §5.4). Las listas que contiene dentro, como `projection`, sí son arrays normales dentro del objeto.
- **Errores**: `403` si el usuario no pertenece al grupo.

## 5. Reglas de negocio

- **La aritmética de previsión vive en el servidor, no en el cliente.** `real_balance`, `daily_safe_spend` y `projection` son cálculos derivados, y repetirlos en cada cliente garantiza que acaben divergiendo. Además, aquí se pueden probar: son funciones puras de Python que reciben saldo, fechas y planes, y no dependen de la base de datos.
  - `real_balance = available − Σ(gastos fijos pendientes)`. Se usa `available`, no `net_worth`: el dinero de la cuenta de ahorro no es de donde sale la compra del súper (`accounts.md` §5).
  - `daily_safe_spend = real_balance / días restantes`, redondeado a la baja, en céntimos.
  - `projection` es una curva escalonada: parte del saldo de hoy y resta cada gasto fijo el día que vence. Un plan ya vencido (`next_due_date` anterior a hoy, porque el cron aún no ha corrido) se ancla a hoy — su dinero todavía tiene que salir, pero no puede dibujarse antes del inicio de la curva.
  - **La curva termina el día del cobro pero antes de cobrar**: no suma el ingreso de la nómina. Es "con cuánto llego a fin de ciclo", no "cuánto tendré después de cobrar". Por construcción, su último punto es igual a `real_balance` — los dos restan el mismo conjunto de gastos fijos, así que si alguna vez divergen es que hay un error en uno de los dos.
  - Se calcula en Python, no con `generate_series` en SQL: son como mucho 31 puntos, así que el SQL no aportaría nada medible, y en cambio una función pura sí se puede probar sin base de datos.
- **El día del cobro, `days_remaining` vale cero.** Antes de que corra el cron, el ancla todavía apunta a hoy. Dividir por él revienta con `ZeroDivisionError`, y es un fallo garantizado, no hipotético: ocurre una vez al mes, siempre. El divisor se acota a un mínimo de 1.
- **El horizonte del resumen nunca se cierra antes de hoy.** El ancla puede quedar *atrasada*: entre la medianoche y la ejecución del cron —o si el cron falló un día entero— `next_due_date` apunta al pasado. El horizonte es entonces `max(next_due_date, hoy)`, y eso resuelve dos cosas a la vez: `days_remaining` nunca sale negativo (un "−1 días restantes" no significa nada para quien lee la pantalla), y un gasto que vence hoy no queda fuera de `real_balance` por caer después de un vencimiento ya pasado. La proyección usa el mismo horizonte, así que en ese caso devuelve un único punto en lugar de una lista vacía, y se conserva la igualdad entre su último punto y `real_balance`.
- Un grupo siempre tiene al menos un `owner` mientras tenga algún miembro. El único `owner` de un grupo con otros miembros no puede abandonarlo ni ser eliminado, ni puede degradarse su propio rol, sin que antes se promueva a otro miembro a `owner`. Si es además el único miembro del grupo, sí puede abandonarlo — el grupo queda sin miembros, no se borra ni se archiva automáticamente. Esto resuelve la dependencia que `docs/domains/users.md` §6 dejaba abierta sobre la baja de un usuario que sea único `owner` de un grupo con más miembros: ese caso debe bloquearse aquí, en `account_groups`, antes de que `users` pueda implementar `DELETE /me`.
- Los roles son jerárquicos para las acciones de gestión: `owner` puede todo lo que puede `admin`; `admin` puede invitar y expulsar `member`, pero no a otro `admin` ni a un `owner`. Cualquier miembro, sea cual sea su rol, puede ver los datos del grupo y abandonar voluntariamente (salvo la restricción de único `owner`).
- Duración de una invitación: 7 días desde su creación. El código no se reutiliza tras aceptarse ni tras expirar; una invitación caducada requiere crear una nueva.
- **Gestionar invitaciones es gobierno del grupo**: listarlas y revocarlas exige `owner`/`admin`, el mismo corte que ya aplica a crearlas. No tendría sentido que quien no puede invitar sí pudiera ver a quién se ha invitado o cortar la invitación de otro.
- **Solo se revoca lo que nadie ha usado.** Una invitación `pending` o `expired` se borra sin más; una `accepted` devuelve `409`, porque su fila es el registro de que alguien entró al grupo y borrarla reescribiría un hecho. Para deshacer eso está el endpoint de expulsar miembros, que es lo que corresponde.
- **Revocar borra la fila, no la marca.** La tabla es un registro histórico —de ahí los `ON DELETE SET NULL` de `invited_by`/`accepted_by`—, pero lo que ese histórico protege son las invitaciones *aceptadas*. Una pendiente que se revoca es una que nadie llegó a usar: no hay hecho que preservar, solo una intención retirada. Consecuencia asumida: **no queda rastro de quién revocó ni cuándo**. El razonamiento completo y las alternativas descartadas están en [ADR-0006](../decisions/0006-revocar-invitaciones-borrado-fisico.md).
- **La caducidad perezosa es una sola regla, aplicada en dos sitios.** Tanto el `GET` por código como el listado por grupo marcan `expired` lo que ya haya caducado, en el momento de leerlo. No hay proceso en segundo plano. Si el listado no lo hiciera, la pantalla de gestión mostraría como pendientes invitaciones caducadas hace semanas que nadie ha consultado.
- La divisa única por grupo (`accounts.currency`, no `account_groups.currency`) se valida a nivel de aplicación, no de base de datos — ver `ARCHITECTURE.md` §6. La validación concreta se define en el SPEC de `accounts`, todavía sin redactar; este dominio no la implementa.
- El borrado es lógico solo en el sentido de `is_active`: no hay una columna `deleted_at` en `account_groups` (a diferencia de `transactions`). Un grupo archivado conserva todos sus datos y puede reactivarse con el mismo `PATCH`.

## 6. Fuera de alcance (v1)

- Envío de la invitación por email — el `code` se genera y se devuelve al cliente, pero comunicárselo al invitado es responsabilidad del frontend (por ejemplo, compartiendo un enlace).
- Rechazar explícitamente una invitación por parte del invitado (`status = 'expired'` se alcanza por el paso del tiempo o al revocarla quien administra el grupo, nunca por una acción de quien la recibe).
- **Rastro de la revocación**: quién revocó una invitación y cuándo. La fila se borra, así que no queda registrado en ninguna parte (ADR-0006).
- **Reenviar una invitación** como operación propia: el listado devuelve el `code`, y con él el cliente puede reconstruir el enlace sin crear una invitación nueva.
- **Revocar en bloque** todas las invitaciones pendientes de un grupo.
- Roles personalizados más allá de `owner`/`admin`/`member`.
- Borrado físico de un grupo — solo archivado (`is_active = false`).
- Transferencia de propiedad como operación dedicada (se resuelve con `PATCH` de rol, ver sección 4).
- **Configurar el resumen**: `overview` no admite parámetros. No se puede elegir qué bloques devuelve, ni pedirlo con fecha de referencia distinta de hoy, ni cambiar el horizonte de la proyección.
- **Comparar periodos** ("este mes frente al anterior") o cualquier serie histórica: el resumen describe el estado actual y lo que queda hasta el cobro, nada más.
- **Cachear el resumen**: se calcula entero en cada petición. A los volúmenes de `ARCHITECTURE.md` §9 no compensa la invalidación.

## 7. Criterios de aceptación

- Crear un grupo crea también, en la misma operación, la fila de `account_group_members` con `role = 'owner'` para quien lo creó.
- El listado de grupos incluye a quien consulta dentro de `members`, con su rol, de modo que el cliente puede resolver qué le está permitido en cada grupo sin una segunda petición.
- Consultar una invitación con un código inexistente devuelve `404`; con un código válido pero ya `accepted` o expirado, devuelve `200` con el `status` real, no un error.
- Consultar una invitación por su código devuelve el grupo completo embebido, de modo que un usuario que no pertenece al grupo puede ver su nombre sin tener acceso a `GET /account-groups`.
- El listado por grupo devuelve las invitaciones en cualquier estado, cada una con su `code`, y **sin** el grupo embebido.
- Listar un grupo con una invitación `pending` cuyo `expires_at` ya pasó la devuelve como `expired`, y la fila queda marcada así en base de datos.
- Revocar una invitación `pending` devuelve `204` y la fila desaparece del listado; repetir la llamada devuelve `404`.
- Revocar una invitación `accepted` devuelve `409` y no borra nada: quien ya entró al grupo se saca expulsándolo, no borrando su invitación.
- Revocar una invitación `expired` sí funciona: no aporta nada y ensucia la pantalla.
- Revocar con un `invitation_id` de otro grupo devuelve `404`, sin distinguirlo de uno inexistente.
- Un miembro con rol `member` recibe `403` al listar o al revocar invitaciones.
- Consultar una invitación `pending` cuyo `invited_by` ha borrado su cuenta la marca `expired` en ese momento y la devuelve con `invited_by: null`, sin dar ningún error.
- Aceptar una invitación con un `invitation_id` inexistente, o que existe pero no pertenece al `group_id` de la ruta, devuelve `404`, sin distinguir entre ambos casos.
- Aceptar una invitación ya aceptada, expirada por tiempo, expirada por invitador borrado, o siendo ya miembro del grupo, devuelve `409`, sin crear una fila de pertenencia.
- Aceptar una invitación válida crea la fila de `account_group_members` con el rol de la invitación, y marca la invitación `accepted` con `accepted_by`/`accepted_at` rellenos.
- Intentar que el único `owner` de un grupo con otros miembros lo abandone, sea eliminado, o cambie su propio rol, devuelve `409`, sin aplicar el cambio.
- El único `owner` y único miembro de un grupo sí puede abandonarlo.
- Un usuario autenticado pero sin pertenencia al grupo recibe `403` al operar sobre él, nunca `404`.
- Un `admin` que intenta expulsar a un `owner` recibe `403`.

### Resumen del grupo

- Un grupo con nómina mensual el día 5 y dos gastos fijos antes de esa fecha devuelve un `payday` correcto, `real_balance = available − la suma de esos dos gastos`, y una `projection` con un escalón en la fecha de cada uno.
- Archivar el plan de la nómina deja el resumen respondiendo `200`, con `payday`, `days_remaining`, `daily_safe_spend` y `projection` a `null`, pero `net_worth`, `available` y el gasto de hoy con sus valores reales.
- Consultado el mismo día del cobro, `days_remaining` es cero y el endpoint responde `200` — no un `500` por división entre cero.
- Con el ancla atrasada (`next_due_date` de ayer, porque el cron no ha corrido), `days_remaining` es cero y no un número negativo, y un gasto que vence hoy sí entra en `real_balance`.
- El plan de la nómina **no** aparece entre `pending_fixed_expenses`, aunque su fecha esté dentro del rango.
- Una transferencia programada dentro del rango tampoco aparece entre los gastos fijos pendientes (limitación conocida, `payment_plans.md` §6).
- El último punto de `projection` coincide exactamente con `real_balance`: la curva termina **el día del cobro pero antes de cobrar**, así que los dos números restan el mismo conjunto de gastos fijos. Si divergen, hay un error en uno de los dos.
- Con dos gastos fijos que vencen el mismo día, la curva muestra un único escalón que acumula ambos, no dos escalones el mismo día.

> Estos criterios se verifican a mano contra la base real en lo que toca a los agregados; la aritmética (proyección, gasto diario seguro, exclusión del ancla) sí es testeable unitariamente, porque son funciones puras.
