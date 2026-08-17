# SPEC de dominio — transactions

## 1. Problema

Las cuentas (`accounts`) tienen saldo, pero nada registra cómo se llegó a él: cada ingreso, gasto o transferencia entre cuentas necesita quedar anotado, con fecha, importe y opcionalmente una categoría, para que el `balance` derivado de una cuenta tenga detrás un histórico real que lo explique — no un número que cambia por arte de magia.

## 2. Relación con otros dominios

Depende de `accounts` (`account_id`/`to_account_id` referencian `Account`, siempre dentro del mismo `account_group` — ver sección 5), de `categories` (`category_id`, opcional) y de `users` (`created_by`/`updated_by`). Es la base de la que depende `payment_plans`: un plan de pago, al vencer, generará una `transaction` real (`payment_plan_id` en la tabla, ver más abajo) — pero esa generación es responsabilidad del SPEC de `payment_plans`, no de este.

**`payment_plan_id` no existe todavía en la migración de este dominio.** `payment_plans` aún no está implementado, así que no hay tabla a la que referenciar; se añadirá como columna nullable (`ON DELETE SET NULL`) mediante un `ALTER TABLE` en la propia migración de `payment_plans`, cuando le toque. Mismo patrón ya usado entre `accounts` y `transactions`: `trg_init_account_balance` se creó en la migración de `accounts` porque su propio endpoint de creación lo necesitaba, y los triggers que mantienen `balance` al día con las transacciones se crean aquí, no allí.

Todos los endpoints cuelgan de una cuenta concreta (`/api/v1/accounts/{account_id}/transactions`, ver `ARCHITECTURE.md` §8.1) y reutilizan sin cambios `RequireAccountMembership` de `accounts/dependencies.py` — a diferencia de `accounts`/`categories`, aquí **no** se exige rol `owner`/`admin`: cualquier miembro del grupo puede operar transacciones, tal y como ya anticipaba `accounts.md` §5 ("una transacción es una anotación cotidiana, frecuente y de bajo riesgo").

## 3. Casos de uso

- Un miembro, sea cual sea su rol, registra un ingreso o un gasto en una cuenta de su grupo, opcionalmente categorizado.
- Un miembro registra una transferencia entre dos cuentas de su mismo grupo.
- Un miembro consulta el histórico paginado de una cuenta, o el detalle de una transacción concreta — incluidas las transferencias que esa cuenta ha recibido, no solo las que ha originado.
- Un miembro corrige el importe, la categoría, la fecha o las notas de una transacción ya registrada.
- Un miembro borra (lógicamente) una transacción registrada por error, revirtiendo su efecto sobre el saldo.
- El saldo de la(s) cuenta(s) implicadas se actualiza automáticamente al crear, editar o borrar una transacción — la aplicación nunca escribe `balance` directamente (mismo principio que `accounts.md` §5).

## 4. Endpoints

Prefijo de recurso: `/api/v1/accounts/{account_id}/transactions` — anidado bajo `accounts` a propósito, a diferencia de `accounts`/`categories`: `ARCHITECTURE.md` §8.1 ya fija que el acceso a transacciones ocurre siempre en el contexto de una cuenta concreta, nunca agregando todas las cuentas de un grupo en una sola consulta, así que aquí no hay el mismo dilema de "mezclar dominios en la URL" que llevó a `group_id` como query param en los otros dos.

### `POST /api/v1/accounts/{account_id}/transactions`

Requiere pertenencia al grupo de la cuenta, cualquier rol.

- **Entrada**: `type` (`income`/`expense`/`transfer`), `amount` (entero positivo, la magnitud — ver sección 5 sobre el signo), `category_id` (opcional, solo válido si `type` no es `transfer`), `to_account_id` (obligatorio si `type = transfer`, prohibido en el resto), `date`, `notes` (opcional).
- **Efecto**: si `type` es `income`/`expense`, crea una única fila con el signo de `amount` derivado por el servidor según `type` (ver sección 5). Si `type = transfer`, crea **dos** filas — partida doble, ver sección 5 —, una en `account_id` (origen, `amount` negativo) y otra en `to_account_id` (destino, `amount` positivo), enlazadas por un `transfer_group_id` compartido. En ambos casos, el saldo de la(s) cuenta(s) implicadas se actualiza automáticamente vía trigger.
- **Salida**: la transacción creada, con `amount` ya firmado tal y como queda almacenado. Para una transferencia, se devuelve la pata que corresponde a `account_id` (la cuenta de la URL) — la pata de `to_account_id` se consulta desde el listado o detalle de esa otra cuenta.
- **Errores**: `403` si no pertenece al grupo de la cuenta. `422` si la combinación `type`/`category_id`/`to_account_id` es estructuralmente inválida (ver sección 5), o si `amount` no es positivo. `409` si `category_id` pertenece a otro grupo, o si `to_account_id` no existe, pertenece a otro grupo, o coincide con `account_id`.

### `GET /api/v1/accounts/{account_id}/transactions`

Requiere pertenencia al grupo de la cuenta, cualquier rol. Paginado (`ARCHITECTURE.md` §5.4, `limit`/`offset`) — el único listado paginado del proyecto, ya anticipado en `ARCHITECTURE.md` §8.1/§9.2.

- **Salida**: las transacciones activas (no borradas) de la cuenta — filtrando únicamente por `account_id = {account_id}`, sin ningún caso especial — ordenadas por `date` descendente, envueltas en `PaginatedResponse` (`items`, `total`, `limit`, `offset`). Gracias a la partida doble, esto incluye tanto los movimientos originados en esta cuenta como las transferencias recibidas desde otra: cada una es su propia fila con `account_id` igual a esta cuenta.
- **Errores**: `403` si no pertenece al grupo de la cuenta.

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

## 5. Reglas de negocio

- **Cualquier miembro puede operar transacciones**, sin distinción de rol — a diferencia de `accounts`/`categories`, donde crear/editar/archivar es cosa de `owner`/`admin`. Registrar un movimiento cotidiano es justo el caso de uso que `accounts.md` §5 dejaba fuera de la restricción de gobierno del grupo.
- **Una transferencia se guarda como dos filas (partida doble), no una** — cada fila afecta al balance de una única cuenta, la suya. La pata en `account_id` (origen) lleva `amount` negativo; la pata en `to_account_id` (destino) lleva `amount` positivo; ambas comparten `transfer_group_id`. Se descartó el diseño de una sola fila con dos cuentas (`account_id` + `to_account_id`) porque obligaba a consultar cada cuenta de forma asimétrica: el listado de la cuenta destino necesitaría un `WHERE account_id = :id OR to_account_id = :id` para ver sus transferencias entrantes, en vez del mismo `WHERE account_id = :id` que ya usa cualquier otra consulta del proyecto. Con partida doble, cada cuenta consulta solo sus propias filas, sin excepciones.
- **El signo de `amount` lo decide el servidor, no el cliente**: la entrada siempre es una magnitud positiva; a partir de `type`, el servicio la persiste como `+amount` (`income`), `-amount` (`expense`), o como el par `-amount`/`+amount` en las dos patas de un `transfer`. Pedirle al cliente que mande ya el signo correcto es una fuente de errores completamente evitable — el propio `type` ya contiene esa información. La salida (`TransactionRead.amount`), en cambio, sí devuelve el valor firmado tal y como queda en base de datos, igual que `accounts.balance`.
- **Las dos patas de una transferencia se mantienen sincronizadas por un trigger de base de datos** (`trg_sync_transfer_pair`), no por código de la aplicación: al editar o borrar lógicamente una pata, el trigger localiza a su pareja (por `transfer_group_id`) y replica `amount` (invertido), `date`, `notes` y `deleted_at`. Así ni un `UPDATE` hecho a mano en `psql`, saltándose la aplicación por completo, puede descuadrar el par — mismo nivel de garantía que ya tienen `balance` (vía trigger) o la profundidad de `categories` (vía trigger), no una validación que solo vive en `service.py`.
- **Estructura por `type`**, validada en el propio schema de entrada (un `model_validator` de Pydantic, no en `service.py`: es consistencia entre campos del mismo cuerpo de la petición, no una regla que dependa de otra tabla, así que encaja como validación de forma — `422` — y no de negocio — `409`):
  - `income`/`expense`: `to_account_id` no se admite. `category_id` es opcional.
  - `transfer`: `to_account_id` es obligatorio y debe ser distinto de `account_id` (impuesto también por `CHECK chk_transfer_to_account`). `category_id` no se admite — una transferencia es un movimiento interno, ni ingreso ni gasto categorizable.
- **`category_id` debe pertenecer al mismo grupo que la cuenta** — lo impone un trigger de base de datos (`check_transaction_category_group`), y se valida también en la aplicación para devolver un `409` claro en vez de dejar que un error interno de Postgres llegue sin traducir.
- **`to_account_id` debe pertenecer al mismo grupo que `account_id`**: esto no lo impone ningún trigger — a diferencia de `category_id`, no hay invariante de base de datos que lo cubra — así que es una validación exclusivamente de aplicación, mismo patrón que el hueco ya documentado en `categories.md` §5.
- **`type` solo es editable entre `income` y `expense`**: es un cambio de signo sin más consecuencias (`category_id` sigue siendo válido en ambos). Nunca se puede convertir una transacción en `transfer`, ni convertir una `transfer` ya existente en otra cosa — eso exigiría crear/destruir una segunda fila y un `to_account_id`, no es un simple cambio de campo. Si una transferencia se registró mal, se borra (borrado lógico) y se crea de nuevo. `account_id` y `to_account_id` tampoco son editables, por la misma razón de fondo: ligados a una fila y, en el caso de `transfer`, a su pareja.
- **El saldo nunca se escribe desde la aplicación**: `trg_transactions_balance_update` aplica o revierte el efecto de cada `INSERT`/`UPDATE`/`DELETE` sobre `balance`, siempre sobre la cuenta propia de la fila (`account_id`) — sin caso especial para `transfer`, ya que cada pata ya solo afecta a una cuenta.
- **Borrado lógico, no físico** (`ARCHITECTURE.md` §8.2, la única excepción del proyecto a "el borrado físico es la convención por defecto"): una transacción borrada dispara la reversión de su efecto sobre el saldo, y desaparece de listados y detalle. No hay endpoint de restauración en v1, aunque el propio trigger de balance ya sabe revertir ese caso si algún día hace falta exponerlo.
- Igual que en el resto de dominios, un error de autorización nunca se enmascara como recurso inexistente: no pertenecer al grupo de la cuenta da `403`, nunca `404`. Un `transaction_id` que no cuadra con el `account_id` de la ruta sí da `404` (no `403`): la pertenencia al grupo ya ha quedado demostrada por el propio `account_id`, no es un fallo de autorización.

## 6. Fuera de alcance (v1)

- Filtros de listado (por categoría, rango de fechas, tipo) — el único parámetro de `GET` es la paginación (`limit`/`offset`).
- Restaurar una transacción borrada lógicamente — el trigger de balance lo soporta a nivel de base de datos, pero ningún endpoint lo expone.
- Editar `account_id` o `to_account_id` de una transacción ya creada, o cambiar `type` hacia/desde `transfer`.
- Una restricción de base de datos que garantice que todo `transfer_group_id` tiene exactamente dos filas (por ejemplo, un `CONSTRAINT TRIGGER ... DEFERRABLE` verificado al final de la transacción) — el par se crea siempre junto, en la misma petición/commit, desde `service.py`; se deja como posible mejora futura si alguna vez se necesita blindarlo también contra un `INSERT` manual incompleto.
- Propagar un `DELETE` físico directo entre las dos patas de una transferencia — no lo cubre ningún trigger, pero tampoco hay ningún endpoint que exponga borrado físico (ver punto anterior de `ARCHITECTURE.md` §8.2).
- `ocr_receipt_ref`: columna reservada en el diseño de referencia para una futura integración de reconocimiento de recibos (identificador de un documento en MongoDB); ningún endpoint de v1 la lee ni la escribe.
- `payment_plan_id`: no existe todavía en este dominio (ver sección 2) — llegará con la migración de `payment_plans`.
- Saldo agregado por grupo (ya mencionado como pendiente en `accounts.md` §6).
- La conversión de un `payment_plan` vencido en una `transaction` real — corresponde al SPEC de ese dominio, no a este.

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
