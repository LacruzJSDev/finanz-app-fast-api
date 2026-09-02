# SPEC de dominio — categories

## 1. Problema

Las transacciones necesitan clasificarse (comida, transporte, nómina...) para que un grupo pueda entender en qué se le va o le entra el dinero. Sin categorías, `transactions` solo tendría importes sueltos sin ningún criterio para agruparlos o analizarlos.

## 2. Relación con otros dominios

Depende de `account_groups` (toda categoría pertenece a un `account_group`, nunca a un usuario directamente) y de `users` (`created_by`/`updated_by` referencian `User`). Es la base de la que dependen `payment_plans` y `transactions` — ambos referencian `category_id` de forma opcional (`ON DELETE SET NULL`: archivar o borrar una categoría no debe destruir movimientos ya registrados con ella).

La categoría es agnóstica al tipo de movimiento (ingreso/gasto) — ese dato vive en `transactions.type`, no aquí, porque una misma categoría puede aplicarse en principio a ambos.

## 3. Casos de uso

- Un miembro con rol `owner` o `admin` crea una categoría raíz, o una subcategoría de una raíz existente.
- Un miembro, sea cual sea su rol, consulta las categorías de un grupo, o el detalle de una categoría concreta.
- Un miembro con rol `owner` o `admin` actualiza los datos de una categoría (nombre, categoría padre, color, icono) o la archiva.

## 4. Endpoints

Prefijo de recurso: `/api/v1/categories` — mismo patrón que `accounts.md` §4: `group_id` como query param en los dos endpoints de colección (`POST`, `GET`), nunca en el body ni anidado bajo `/account-groups/{group_id}/...`, y los endpoints con `{category_id}` en la ruta resuelven la pertenencia a partir de la propia categoría. La autorización reutiliza el mismo par fábrica/`check_group_role` ya construido para `accounts` (`require_account_role` como referencia directa) — aquí sería `require_category_role`.

### `POST /api/v1/categories?group_id={group_id}`

Requiere rol `owner` o `admin` en `group_id`.

- **Entrada**: `name`, `parent_id` (opcional — si se omite, la categoría nace raíz), `color` (opcional), `icon` (opcional).
- **Efecto**: crea la categoría.
- **Salida**: la categoría creada.
- **Errores**: `403` si el usuario no pertenece a `group_id`, o pertenece pero con rol `member`. `409` si `parent_id` no existe, pertenece a otro grupo, o no es ella misma una categoría raíz (ver regla de negocio — parte de esto lo impone un trigger de base de datos, parte se valida en la aplicación).

### `GET /api/v1/categories?group_id={group_id}`

Requiere pertenencia al grupo, cualquier rol.

- **Salida**: las categorías del grupo (activas y archivadas, raíces y subcategorías juntas — el cliente arma el árbol con `parent_id`), envueltas en `{items: [...]}`, sin paginar.
- **Errores**: `403` si el usuario no pertenece a `group_id`.

### `GET /api/v1/categories/{category_id}`

Requiere pertenencia al grupo de la categoría.

- **Salida**: el detalle de la categoría.
- **Errores**: `403` si el usuario no pertenece al grupo de la categoría — nunca `404`, ni siquiera si la categoría no existe (mismo criterio que `accounts.md`).

### `PATCH /api/v1/categories/{category_id}`

Requiere rol `owner` o `admin` en el grupo de la categoría. Actualización parcial (`ARCHITECTURE.md` §5.5).

- **Entrada**: `name`, `parent_id`, `color`, `icon`, `is_active` — todos opcionales.
- **Efecto**: `is_active = false` archiva la categoría; no existe borrado físico en v1 (ver sección 6).
- **Errores**: `400` si no se incluye ningún campo. `403` si el usuario no pertenece al grupo de la categoría, o pertenece pero con rol `member`. `409` si el nuevo `parent_id` viola la regla de jerarquía (ver sección 5).

## 5. Reglas de negocio

- `created_by` conserva quien creó la categoría y `updated_by` quien realizó el último cambio humano, incluido archivarla o reactivarla mediante `PATCH`. Son referencias opcionales a `users` para preservar el histórico si se elimina una identidad.
- **Jerarquía a dos niveles**, impuesta en parte por la base de datos: el trigger `trg_check_category_depth` rechaza que una categoría se referencie a sí misma como padre, y que `parent_id` apunte a algo que ya tiene su propio `parent_id` (es decir, el padre siempre tiene que ser una raíz). Esto la aplicación no puede saltárselo ni por error.
- **Lo que el trigger no cubre, y hay que validar en la aplicación**: que `parent_id` pertenezca al mismo `group_id` que la categoría — la base de datos no lo impone (a diferencia de la profundidad, no hay ninguna restricción que lo garantice), así que un `parent_id` de otro grupo tiene que rechazarse a mano, mismo patrón que la divisa única por grupo en `accounts.md` §5. Tampoco cubre el caso inverso: asignarle un `parent_id` a una categoría que **ya tiene subcategorías propias** convertiría a esas subcategorías en un tercer nivel sin que el trigger se entere (solo mira hacia arriba en la cadena de `parent_id`, no si la propia fila tiene hijos) — se valida también en la aplicación.
- **Gestionar categorías es gobierno del grupo, no uso cotidiano**: crear, editar y archivar requiere rol `owner` o `admin`, mismo corte que `accounts.md` §5 — leer está abierto a cualquier rol.
- Igual que en `accounts`/`account_groups`, un error de autorización nunca se enmascara como recurso inexistente: no pertenecer al grupo de una categoría da `403`, nunca `404`, tanto si la categoría existe como si no.
- El borrado es lógico solo en el sentido de `is_active`, igual que `accounts`. Archivar una categoría **no** archiva en cascada sus subcategorías ni afecta a transacciones ya registradas con ella — solo dejaría de aparecer como opción al categorizar movimientos nuevos (comportamiento que definirá el propio SPEC de `transactions`).

## 6. Fuera de alcance (v1)

- Más de dos niveles de jerarquía.
- Reordenar categorías (no hay ningún campo de orden/posición en el schema).
- Categorías predefinidas o compartidas entre grupos — cada grupo empieza sin ninguna, se crean a mano.
- Fusionar categorías o reasignar en bloque las transacciones de una categoría archivada a otra.
- Borrado físico de una categoría — solo archivado (`is_active = false`).

## 7. Criterios de aceptación

- Crear una categoría sin `parent_id` la deja como raíz.
- Crear una categoría con `parent_id` de una raíz existente del mismo grupo funciona.
- Crear una categoría cuyo `parent_id` apunta a una categoría que ya tiene padre (es decir, a una subcategoría) devuelve `409`, sin crearla — lo bloquea el trigger de base de datos.
- Crear o editar una categoría con `parent_id` de un grupo distinto devuelve `409`, sin aplicar el cambio.
- Asignarle `parent_id` a una categoría que ya tiene subcategorías propias devuelve `409`, sin aplicar el cambio.
- Un `PATCH` sin ningún campo devuelve `400`, sin aplicar ningún cambio.
- Un miembro con rol `member` que intenta crear, editar o archivar una categoría recibe `403`; consultar categorías sí le funciona con cualquier rol.
- Un usuario autenticado pero sin pertenencia al grupo de la categoría recibe `403` al operar sobre ella, tanto si la categoría existe como si no.
- Archivar una categoría con subcategorías activas no las archiva a ellas ni las desvincula de su padre.
