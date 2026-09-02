# SPEC de dominio — transactions

## 1. Problema

Las cuentas (`accounts`) tienen saldo, pero nada registra cómo se llegó a él: cada ingreso, gasto o transferencia entre cuentas necesita quedar anotado, con fecha, importe y opcionalmente una categoría, para que el `balance` derivado de una cuenta tenga detrás un histórico real que lo explique — no un número que cambia por arte de magia.

## 2. Relación con otros dominios

Depende de `accounts` (`account_id`/`to_account_id` referencian `Account`, siempre dentro del mismo `account_group` — ver sección 5), de `categories` (`category_id`, opcional) y de `users` (`created_by`/`updated_by`). Es la base de la que depende `payment_plans`: un plan de pago, al vencer, generará una `transaction` real (`payment_plan_id` en la tabla, ver más abajo) — pero esa generación es responsabilidad del SPEC de `payment_plans`, no de este.

`payment_plan_id` se añadió como columna nullable (`ON DELETE SET NULL`) desde la propia migración de `payment_plans` (`10716e6808f4`), no desde la de este dominio: cuando se implementó `transactions` no existía todavía la tabla a la que referenciar. Es el mismo patrón ya usado entre `accounts` y `transactions` — `trg_init_account_balance` se creó en la migración de `accounts` porque su propio endpoint de creación lo necesitaba, y los triggers que mantienen `balance` al día con las transacciones se crean aquí, no allí.

También es la fuente de la que se alimenta `budgets`: el gasto real contra el que se compara un presupuesto sale de agregar transacciones (ver `budgets.md` §2), pero ese cálculo vive allí, no aquí.

Este dominio expone **dos routers**, y la distinción importa:

- **CRUD anidado bajo la cuenta** (`/api/v1/accounts/{account_id}/transactions`): crear, leer una, editar y borrar. Una transacción pertenece a una cuenta y solo a una, así que operar sobre ella cuelga de esa cuenta. Reutiliza sin cambios `RequireAccountMembership` de `accounts/dependencies.py`.
- **Consulta plana bajo el grupo** (`/api/v1/transactions`): listar con filtros, buscar y agregar. El ámbito es el grupo y la cuenta es un filtro más (`ARCHITECTURE.md` §8.3, [ADR-0002](../decisions/0002-router-plano-de-consulta.md)). Usa `RequireMembership` de `account_groups/dependencies.py`, resuelto sobre el `group_id` del query param.

En ninguno de los dos se exige rol `owner`/`admin`, a diferencia de `accounts`/`categories`: cualquier miembro del grupo puede operar y consultar transacciones, tal y como ya anticipaba `accounts.md` §5 ("una transacción es una anotación cotidiana, frecuente y de bajo riesgo").

## 3. Casos de uso

- Un miembro, sea cual sea su rol, registra un ingreso o un gasto en una cuenta de su grupo, opcionalmente categorizado.
- Un miembro registra una transferencia entre dos cuentas de su mismo grupo.
- Un miembro consulta el histórico paginado de una cuenta, o el detalle de una transacción concreta — incluidas las transferencias que esa cuenta ha recibido, no solo las que ha originado.
- Un miembro busca movimientos por texto ("¿cuánto llevo gastado en *mercadona*?"), acotando por categoría, tipo, rango de fechas o cuenta, en todo el grupo o en una cuenta suelta.
- Un miembro revisa qué movimientos quedaron sin categorizar, para clasificarlos y que los desgloses por categoría sean fiables.
- Un miembro consulta cuánto se ha ingresado y gastado en un periodo, desglosado por categoría raíz, para alimentar gráficas — tanto de una cuenta concreta como del grupo entero.
- Un miembro consulta cuánto se ha gastado hoy y en cuántos movimientos.
- Un miembro corrige el importe, la categoría, la fecha o las notas de una transacción ya registrada.
- Un miembro borra (lógicamente) una transacción registrada por error, revirtiendo su efecto sobre el saldo.
- El saldo de la(s) cuenta(s) implicadas se actualiza automáticamente al crear, editar o borrar una transacción — la aplicación nunca escribe `balance` directamente (mismo principio que `accounts.md` §5).

## 4. Endpoints

Dos prefijos, uno por cada cosa que se hace con una transacción (ver sección 2):

- **`/api/v1/accounts/{account_id}/transactions`** — CRUD. Anidado bajo la cuenta porque una transacción pertenece a una cuenta concreta.
- **`/api/v1/transactions`** — consulta. Plano, con `group_id` obligatorio, porque consultar es una pregunta de grupo (`ARCHITECTURE.md` §8.3).

### 4.A CRUD anidado bajo la cuenta

### `POST /api/v1/accounts/{account_id}/transactions`

Requiere pertenencia al grupo de la cuenta, cualquier rol.

- **Entrada**: `type` (`income`/`expense`/`transfer`), `amount` (entero positivo, la magnitud — ver sección 5 sobre el signo), `category_id` (opcional, solo válido si `type` no es `transfer`), `to_account_id` (obligatorio si `type = transfer`, prohibido en el resto), `date`, `notes` (opcional).
- **Efecto**: si `type` es `income`/`expense`, crea una única fila con el signo de `amount` derivado por el servidor según `type` (ver sección 5). Si `type = transfer`, crea **dos** filas — partida doble, ver sección 5 —, una en `account_id` (origen, `amount` negativo) y otra en `to_account_id` (destino, `amount` positivo), enlazadas por un `transfer_group_id` compartido. En ambos casos, el saldo de la(s) cuenta(s) implicadas se actualiza automáticamente vía trigger.
- **Salida**: la transacción creada, con `amount` ya firmado tal y como queda almacenado. Para una transferencia, se devuelve la pata que corresponde a `account_id` (la cuenta de la URL) — la pata de `to_account_id` se consulta desde el listado o detalle de esa otra cuenta.
- **Errores**: `403` si no pertenece al grupo de la cuenta. `422` si la combinación `type`/`category_id`/`to_account_id` es estructuralmente inválida (ver sección 5), o si `amount` no es positivo. `409` si `category_id` pertenece a otro grupo, o si `to_account_id` no existe, pertenece a otro grupo, o coincide con `account_id`.

### `GET /api/v1/accounts/{account_id}/transactions`

Requiere pertenencia al grupo de la cuenta, cualquier rol. Paginado (`ARCHITECTURE.md` §5.4, `limit`/`offset`), sin filtros.

- **Salida**: las transacciones activas (no borradas) de la cuenta — filtrando únicamente por `account_id = {account_id}`, sin ningún caso especial — ordenadas por `date` descendente, envueltas en `PaginatedResponse` (`items`, `total`, `limit`, `offset`). Gracias a la partida doble, esto incluye tanto los movimientos originados en esta cuenta como las transferencias recibidas desde otra: cada una es su propia fila con `account_id` igual a esta cuenta.
- **Errores**: `403` si no pertenece al grupo de la cuenta.

> **Camino heredado.** `GET /api/v1/transactions?group_id=G&account_id={account_id}` devuelve exactamente lo mismo, y además admite filtros. Este endpoint se conserva sin cambios porque `ARCHITECTURE.md` §5.1 prohíbe romper un contrato ya publicado dentro de `/api/v1`; lo natural es retirarlo cuando exista una `v2` ([ADR-0002](../decisions/0002-router-plano-de-consulta.md)). Para código nuevo, usar el plano.

### `GET /api/v1/accounts/{account_id}/transactions/{transaction_id}`

Requiere pertenencia al grupo de la cuenta.

- **Salida**: el detalle de la transacción.
- **Errores**: `403` si no pertenece al grupo de la cuenta — nunca `404`, mismo criterio de siempre. `404` si la transacción no existe, está borrada, o su `account_id` no coincide con el de la ruta — con partida doble esto ya no necesita ningún caso especial para `to_account_id`: cada pata es una fila normal con su propio `account_id`.

### `PATCH /api/v1/accounts/{account_id}/transactions/{transaction_id}`

Requiere pertenencia al grupo de la cuenta. Actualización parcial (`ARCHITECTURE.md` §5.5).

- **Entrada**: `amount`, `type`, `category_id`, `date`, `notes` — todos opcionales. `type` solo admite alternar entre `income`/`expense`; nunca se puede poner ni quitar `transfer` (ver sección 5). `account_id` y `to_account_id` **no** son editables.
- **Efecto**: el saldo de la cuenta se ajusta automáticamente al nuevo importe vía trigger. Cambiar `type` entre `income`/`expense` invierte el signo almacenado de `amount` aunque no se mande `amount` en la misma petición — se conserva la magnitud, cambia el signo. Si la transacción es una pata de una transferencia, `amount` (con signo invertido), `date` y `notes` se replican automáticamente en su pareja — vía trigger, no vía código de la aplicación (ver sección 5).
- **Errores**: `400` si no se incluye ningún campo. `403`/`404` con el mismo criterio que el `GET` de detalle. `422` si `type = transfer`. `409` si se intenta cambiar el `type` de una transacción que ya es `transfer`, o si el nuevo `category_id` pertenece a otro grupo o no es compatible con el `type` (nuevo o ya fijado) de la transacción.

### `DELETE /api/v1/accounts/{account_id}/transactions/{transaction_id}`

Requiere pertenencia al grupo de la cuenta.

- **Efecto**: borrado lógico (`deleted_at`, `ARCHITECTURE.md` §8.2) — revierte el efecto de la transacción sobre el saldo vía trigger. Si es una pata de una transferencia, su pareja se borra lógicamente también, automáticamente (mismo trigger de sincronización que el `PATCH`). A partir de aquí ambas dejan de aparecer en listados y detalle, como si no existieran para la API, aunque las filas persisten en base de datos por integridad del histórico contable.
- **Salida**: `204 No Content`.
- **Errores**: `403`/`404` con el mismo criterio que el resto de endpoints con `{transaction_id}` — borrar dos veces la misma transacción devuelve `404` la segunda vez, no un `204` silencioso.

### 4.B Consulta plana bajo el grupo

Prefijo `/api/v1/transactions`. Todos requieren pertenencia al grupo (`RequireMembership` sobre `group_id`), cualquier rol.

#### Filtros comunes

Los tres endpoints de esta sección comparten **el mismo juego de query params**, de modo que un agregado describe exactamente las mismas filas que devolvería el listado con esos parámetros (`ARCHITECTURE.md` §8.3).

| Param | Tipo | Obligatorio | Significado |
|---|---|---|---|
| `group_id` | UUID | **sí** | Ámbito. Resuelve la autorización; no es un filtro. |
| `account_id` | UUID | no | Restringe a una cuenta del grupo. |
| `category_id` | UUID | no | Restringe a una categoría. Si es raíz, **incluye sus subcategorías** (sección 5). |
| `uncategorized` | bool | no | `true` devuelve solo lo que no tiene categoría. Excluyente con `category_id`. |
| `type` | enum | no | `income`, `expense` o `transfer`. |
| `date_from` / `date_to` | date | no | Rango inclusivo sobre `date`. |
| `q` | str | no | Subcadena a buscar en `notes`, sin distinguir mayúsculas (sección 5). |

Un filtro ausente no restringe. Ninguno cambia las reglas de visibilidad: las transacciones borradas lógicamente nunca aparecen.

#### `GET /api/v1/transactions`

Paginado (`limit`/`offset`), ordenado por `date` descendente.

- **Salida**: `PaginatedResponse[TransactionRead]` — `items`, `total`, `limit`, `offset`. `total` cuenta las filas que cumplen los filtros, no las del grupo entero.
- **Errores**: `403` si no pertenece al grupo. `409` si `account_id` o `category_id` no pertenecen a `group_id`. `422` si se envían `category_id` y `uncategorized=true` a la vez, o si `date_from` es posterior a `date_to`.

#### `GET /api/v1/transactions/summary`

Desglose de ingresos y gastos por categoría raíz, para gráficas.

- **Salida**: `CollectionResponse[CategorySummaryRead]`, una fila por categoría raíz con `root_category_id`, `root_category_name`, `income`, `expense` y `transaction_count`. Las transacciones sin categoría se agrupan en una fila con `root_category_id` a `null`. Ordenado por nombre de categoría.
- **Efecto sobre el filtrado**: excluye siempre `type = 'transfer'`, incluso si se pide explícitamente — un movimiento interno no es ingreso ni gasto (sección 5).
- **Errores**: los mismos que el listado.

#### `GET /api/v1/transactions/daily`

Lo gastado en un único día. Es el widget "gastado hoy", pero sirve para cualquier fecha.

- **Entrada**: `date` (obligatorio, además de `group_id`). Acepta también `account_id`, y ningún otro filtro.
- **Salida**: `DailySpendRead` — `{date, spent, transaction_count}`. `spent` es la **magnitud** gastada, positiva, aunque en base de datos los gastos se guarden negativos.
- **Errores**: `403` si no pertenece al grupo. `409` si `account_id` no pertenece a `group_id`.

## 5. Reglas de negocio

- `created_by` conserva quien registró el movimiento y `updated_by` quien realizó el último `PATCH` o borrado lógico humano. Son referencias opcionales a `users`; las transacciones materializadas por un plan de pago no tienen actor humano y mantienen ambos campos en `NULL`.
- **Cualquier miembro puede operar transacciones**, sin distinción de rol — a diferencia de `accounts`/`categories`, donde crear/editar/archivar es cosa de `owner`/`admin`. Registrar un movimiento cotidiano es justo el caso de uso que `accounts.md` §5 dejaba fuera de la restricción de gobierno del grupo.
- **Una transferencia se guarda como dos filas (partida doble), no una** — cada fila afecta al balance de una única cuenta, la suya. La pata en `account_id` (origen) lleva `amount` negativo; la pata en `to_account_id` (destino) lleva `amount` positivo; ambas comparten `transfer_group_id`. Se descartó el diseño de una sola fila con dos cuentas (`account_id` + `to_account_id`) porque obligaba a consultar cada cuenta de forma asimétrica: el listado de la cuenta destino necesitaría un `WHERE account_id = :id OR to_account_id = :id` para ver sus transferencias entrantes, en vez del mismo `WHERE account_id = :id` que ya usa cualquier otra consulta del proyecto. Con partida doble, cada cuenta consulta solo sus propias filas, sin excepciones.
- **El signo de `amount` lo decide el servidor, no el cliente**: la entrada siempre es una magnitud positiva; a partir de `type`, el servicio la persiste como `+amount` (`income`), `-amount` (`expense`), o como el par `-amount`/`+amount` en las dos patas de un `transfer`. Pedirle al cliente que mande ya el signo correcto es una fuente de errores completamente evitable — el propio `type` ya contiene esa información. La salida (`TransactionRead.amount`), en cambio, sí devuelve el valor firmado tal y como queda en base de datos, igual que `accounts.balance`.
- **Las dos patas de una transferencia se mantienen sincronizadas por un trigger de base de datos** (`trg_sync_transfer_pair`), no por código de la aplicación: al editar o borrar lógicamente una pata, el trigger localiza a su pareja (por `transfer_group_id`) y replica `amount` (invertido), `date`, `notes` y `deleted_at`. Así ni un `UPDATE` hecho a mano en `psql`, saltándose la aplicación por completo, puede descuadrar el par — mismo nivel de garantía que ya tienen `balance` (vía trigger) o la profundidad de `categories` (vía trigger), no una validación que solo vive en `service.py`.
- **Estructura por `type`**, validada en el propio schema de entrada (un `model_validator` de Pydantic, no en `service.py`: es consistencia entre campos del mismo cuerpo de la petición, no una regla que dependa de otra tabla, así que encaja como validación de forma — `422` — y no de negocio — `409`):
  - `income`/`expense`: `to_account_id` no se admite. `category_id` es opcional.
  - `transfer`: `to_account_id` es obligatorio y debe ser distinto de `account_id` (impuesto también por `CHECK chk_transfer_to_account`). `category_id` no se admite — una transferencia es un movimiento interno, ni ingreso ni gasto categorizable.
- **`category_id` debe pertenecer al mismo grupo que la cuenta** — lo impone un trigger de base de datos (`check_transaction_category_group`), y se valida también en la aplicación para devolver un `409` claro en vez de dejar que un error interno de Postgres llegue sin traducir.
- **`to_account_id` debe pertenecer al mismo grupo que `account_id`**: además de la validación de aplicación que devuelve `409` al cliente, un trigger de PostgreSQL lo impone en `INSERT`/`UPDATE`. Por tanto una escritura directa o un proceso concurrente tampoco puede crear una transferencia entre grupos.
- **`type` solo es editable entre `income` y `expense`**: es un cambio de signo sin más consecuencias (`category_id` sigue siendo válido en ambos). Nunca se puede convertir una transacción en `transfer`, ni convertir una `transfer` ya existente en otra cosa — eso exigiría crear/destruir una segunda fila y un `to_account_id`, no es un simple cambio de campo. Si una transferencia se registró mal, se borra (borrado lógico) y se crea de nuevo. `account_id` y `to_account_id` tampoco son editables, por la misma razón de fondo: ligados a una fila y, en el caso de `transfer`, a su pareja.
- **El saldo nunca se escribe desde la aplicación**: `trg_transactions_balance_update` aplica o revierte el efecto de cada `INSERT`/`UPDATE`/`DELETE` sobre `balance`, siempre sobre la cuenta propia de la fila (`account_id`) — sin caso especial para `transfer`, ya que cada pata ya solo afecta a una cuenta.
- **Borrado lógico, no físico** (`ARCHITECTURE.md` §8.2, la única excepción del proyecto a "el borrado físico es la convención por defecto"): una transacción borrada dispara la reversión de su efecto sobre el saldo, y desaparece de listados y detalle. No hay endpoint de restauración en v1, aunque el propio trigger de balance ya sabe revertir ese caso si algún día hace falta exponerlo.
- Igual que en el resto de dominios, un error de autorización nunca se enmascara como recurso inexistente: no pertenecer al grupo de la cuenta da `403`, nunca `404`. Un `transaction_id` que no cuadra con el `account_id` de la ruta sí da `404` (no `403`): la pertenencia al grupo ya ha quedado demostrada por el propio `account_id`, no es un fallo de autorización.

### Consulta y agregados

- **`account_id` se valida contra `group_id`, y esa validación es de seguridad, no de comodidad.** En el router plano la autorización se resuelve por grupo; si no se comprobara que la cuenta pedida pertenece a ese grupo, cualquier miembro legítimo podría leer los movimientos de otro grupo pasando un `account_id` ajeno. No hay trigger que lo cubra —es el mismo hueco que ya tiene `to_account_id`—, así que se valida en `service.py` y devuelve `409`.
- **Filtrar por una categoría raíz incluye sus subcategorías**; filtrar por una subcategoría devuelve solo la suya. Consultar "Comida" tiene que recoger lo gastado en "Súper" y "Restaurantes", o el número no significa nada. La jerarquía es de exactamente dos niveles (`trg_check_category_depth`), así que la raíz de cualquier categoría está a un solo salto y nunca hace falta una CTE recursiva.
  - **Cuidado: `COALESCE(parent_id, id)` a secas sirve para *agrupar*, pero no para *filtrar*.** Para una subcategoría S con padre P, `COALESCE(S.parent_id, S.id)` vale P, no S: filtrar por S con esa condición sola no devolvería nada. La condición correcta es `COALESCE(parent_id, id) = :cat OR id = :cat` — la primera rama recoge las hijas cuando `:cat` es una raíz, la segunda recoge la categoría pedida en cualquier caso.
  - En el `summary`, en cambio, `COALESCE(parent_id, id)` se usa tal cual como clave de agrupación, y ahí sí es exacto: cada fila cae bajo su raíz.
- **El desglose por categoría excluye siempre `type = 'transfer'`**, aunque se pida ese tipo explícitamente. Una transferencia interna no es ni ingreso ni gasto: al ser partida doble sumaría cero al total, pero aparecería como dos filas (una por cuenta) ensuciando el desglose. El listado sin agregar sí las devuelve — ahí son movimientos reales que el usuario quiere ver.
- **La búsqueda de texto es `notes ILIKE '%término%'`, sin índice.** A los volúmenes de `ARCHITECTURE.md` §9 es instantánea, y evita una extensión de Postgres y una migración. `ILIKE` ignora mayúsculas pero **no** acentos: buscar "nomina" no encuentra "nómina". Si algún día hiciera falta, la salida es `pg_trgm` con índice GIN (rápido) o `unaccent` (insensible a acentos), sin tocar el contrato del endpoint. `notes` es el único campo buscable: no hay `description` ni `merchant` en el modelo.
- **`uncategorized=true` y `category_id` son excluyentes** — pedir ambos es una contradicción sobre el mismo cuerpo de la petición, así que se rechaza con `422` en el schema de entrada, no con `409` en el service (mismo criterio que la consistencia de `type` en el `POST`).
- **`total` cuenta las filas filtradas**, no las del grupo. Un `total` que ignorara los filtros rompería la paginación del cliente.
- **Los importes agregados se devuelven como enteros de céntimos**, igual que `amount` y `balance`. `SUM` sobre `BIGINT` devuelve `NUMERIC` en Postgres, que psycopg entrega como `Decimal`: el repositorio castea explícitamente (`ARCHITECTURE.md` §8.3).
- **`GET /transactions/daily` devuelve la magnitud gastada, positiva**, aunque los gastos se guarden con `amount` negativo. Es el único punto del dominio donde la salida no respeta el signo almacenado, y se hace a propósito: el widget que lo consume muestra "gastado hoy: 26 €", no "−26 €".

## 6. Fuera de alcance (v1)

- **Filtros en el listado anidado** (`GET /accounts/{account_id}/transactions`): sigue admitiendo solo `limit`/`offset`. Los filtros existen únicamente en el router plano (sección 4.B), para no cambiar un contrato ya publicado.
- **Filtro por rango de importes** (`min_amount`/`max_amount`). Se dejó fuera a propósito: los gastos se guardan negativos, así que el filtro tendría que operar sobre la magnitud (`ABS(amount)`) o resultaría contraintuitivo, y esa decisión no se quiso tomar sin un caso de uso real detrás.
- **Ordenación configurable** (`sort`/`order`): el listado siempre va por `date` descendente.
- **Búsqueda insensible a acentos, con stemming, o por relevancia.** `ILIKE` es coincidencia literal de subcadena, sin ranking.
- **Agregados por periodo** (serie mensual, comparativa mes a mes): el resumen agrupa por categoría, no por tiempo. Una gráfica de evolución se construye hoy pidiendo un rango por cada punto.
- **Agregados por cuenta o por tipo de cuenta** como dimensión del `summary`: la única dimensión de agrupación es la categoría raíz.
- Restaurar una transacción borrada lógicamente — el trigger de balance lo soporta a nivel de base de datos, pero ningún endpoint lo expone.
- Editar `account_id` o `to_account_id` de una transacción ya creada, o cambiar `type` hacia/desde `transfer`.
- Una restricción de base de datos que garantice que todo `transfer_group_id` tiene exactamente dos filas (por ejemplo, un `CONSTRAINT TRIGGER ... DEFERRABLE` verificado al final de la transacción) — el par se crea siempre junto, en la misma petición/commit, desde `service.py`; se deja como posible mejora futura si alguna vez se necesita blindarlo también contra un `INSERT` manual incompleto.
- Propagar un `DELETE` físico directo entre las dos patas de una transferencia — no lo cubre ningún trigger, pero tampoco hay ningún endpoint que exponga borrado físico (ver punto anterior de `ARCHITECTURE.md` §8.2).
- `ocr_receipt_ref`: columna reservada en el diseño de referencia para una futura integración de reconocimiento de recibos (identificador de un documento en MongoDB); ningún endpoint de v1 la lee ni la escribe.
- La conversión de un `payment_plan` vencido en una `transaction` real — corresponde al SPEC de ese dominio, no a este.
- El cálculo de gasto real contra presupuesto — corresponde a `budgets.md`, aunque agregue transacciones.

## 7. Criterios de aceptación

- Crear un `income` de `amount = 1000` en una cuenta con `balance = 0` deja el saldo en `1000`.
- Crear un `expense` de `amount = 500` (magnitud positiva enviada por el cliente) resta `500` del saldo de la cuenta — la transacción queda almacenada con `amount = -500`.
- Crear un `transfer` de `amount = 300` entre dos cuentas del mismo grupo resta `300` del saldo de origen, suma `300` al de destino, y genera dos filas con el mismo `transfer_group_id`.
- El listado paginado de la cuenta destino de una transferencia incluye la pata que recibió, sin necesidad de consultarla desde la cuenta origen.
- Editar el `amount` de una pata de una transferencia actualiza también el `amount` (con signo invertido) de su pareja, y ambos saldos quedan correctos.
- Borrar una pata de una transferencia borra lógicamente también a su pareja, y revierte el saldo de las dos cuentas implicadas.
- Crear un `transfer` con `to_account_id` de otro grupo, o igual a `account_id`, devuelve `409`/`422` según corresponda, sin crear ninguna fila ni tocar ningún saldo.
- Crear un `income`/`expense` con `category_id` de otro grupo devuelve `409`, sin crear la transacción.
- Crear un `transfer` con `category_id` devuelve `422`, sin llegar a la base de datos.
- Tras borrar una transacción, su `GET` por id devuelve `404` y deja de aparecer en el listado paginado de la cuenta, aunque la fila sigue en base de datos.
- Cambiar el `type` de un `expense` a `income` sin mandar `amount` invierte el signo almacenado (misma magnitud) y ajusta el saldo en consecuencia.
- Intentar poner `type = transfer` en un `PATCH` devuelve `422`; intentar cambiar el `type` de una transacción que ya es `transfer` devuelve `409`.
- Un `PATCH` sin ningún campo devuelve `400`, sin aplicar ningún cambio.
- Un miembro con rol `member` (no solo `owner`/`admin`) puede crear, editar y borrar transacciones sin recibir `403`.
- Un usuario sin pertenencia al grupo de la cuenta recibe `403` al operar sobre cualquiera de sus transacciones; un `transaction_id` que no pertenece a `account_id` devuelve `404`, no `403`.

### Consulta y agregados

- `GET /transactions?group_id=G` sin más filtros devuelve movimientos de todas las cuentas del grupo; añadir `&account_id=A` devuelve exactamente lo mismo que el listado anidado de esa cuenta.
- Un `account_id` de otro grupo devuelve `409`, aunque el usuario pertenezca legítimamente a `group_id`, y sin filtrar nada.
- Filtrar por una categoría raíz devuelve también los movimientos categorizados en sus subcategorías; filtrar por una subcategoría devuelve solo los suyos.
- `uncategorized=true` devuelve únicamente movimientos con `category_id` nulo; combinarlo con `category_id` devuelve `422`.
- `q=merca` encuentra un movimiento con `notes = "Compra Mercadona"`; `q=MERCA` encuentra el mismo (insensible a mayúsculas); `q=nomina` **no** encuentra uno con `notes = "Nómina"` (sensible a acentos, limitación conocida).
- `date_from` posterior a `date_to` devuelve `422`, sin ejecutar la consulta.
- Una transacción borrada lógicamente no aparece con ningún filtro, incluido `q` sobre un texto que sí contiene.
- `total` refleja el número de filas que cumplen los filtros, no el total del grupo: filtrar por una categoría con 3 movimientos entre 200 devuelve `total = 3`.
- `GET /transactions/summary` no incluye ninguna fila derivada de una transferencia, ni siquiera pasando `type=transfer`.
- En el `summary`, un gasto en una subcategoría aparece sumado bajo su categoría raíz, no como fila propia; los movimientos sin categoría aparecen en una fila con `root_category_id` nulo.
- `GET /transactions/daily` con dos gastos hoy devuelve `spent` positivo igual a la suma de las magnitudes y `transaction_count = 2`; un día sin movimientos devuelve `spent = 0`, no `null`.

> Los criterios de esta sección **se verifican a mano contra la base de datos real**. Los tests unitarios del proyecto sustituyen el repositorio por un `MagicMock`, así que el SQL de los agregados nunca llega a ejecutarse en ellos (`ARCHITECTURE.md` §10).
