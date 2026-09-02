# SPEC de dominio — payment_plans

## 1. Problema

Un grupo sabe de antemano que ciertos movimientos van a ocurrir — una nómina, un alquiler, una suscripción — antes de que ocurran de verdad. Sin este dominio, esos movimientos futuros o recurrentes solo podrían registrarse el día que pasan, como cualquier otra `transaction`, perdiendo la posibilidad de anticiparlos (saber qué va a cobrarse o pagarse antes de que suceda) o de automatizar su registro cuando se repiten cada mes.

## 2. Relación con otros dominios

Depende de `accounts` (`account_id`/`to_account_id`, siempre dentro del mismo `account_group` — mismo criterio que `transactions.md` §5) y de `categories` (`category_id`, opcional). Es quien alimenta a `transactions`: al vencer, un plan genera una `transaction` real, enlazada de vuelta mediante `transactions.payment_plan_id` (columna que se añadió, vacía hasta ahora, en la propia migración de `transactions`).

La generación en sí reutiliza `TransactionService.create_transaction` de `transactions` sin duplicar su lógica: un plan vencido se traduce en el mismo `CreateTransactionCommand` que ya construye el endpoint `POST /accounts/{account_id}/transactions`, con los mismos datos del plan (`account_id`, `type`, `amount`, `category_id`, `to_account_id`, fecha) — así una transferencia generada desde un plan sigue creando sus dos filas por partida doble, con las mismas validaciones de grupo, sin código nuevo para eso.

`type` reutiliza `TransactionTypeEnum` de `transactions` (`income`/`expense`/`transfer`): un plan es la plantilla de la transacción que va a generar, así que necesita saber de antemano de qué tipo será.

## 3. Casos de uso

- Un miembro con rol `owner` o `admin` crea un plan de pago puntual o recurrente en una cuenta de su grupo.
- Un miembro, sea cual sea su rol, consulta los planes de una cuenta, o el detalle de uno concreto.
- Un miembro con rol `owner` o `admin` corrige un plan (importe, categoría, fechas, periodicidad) o lo archiva.
- Un proceso automático diario materializa en `transactions` reales los planes cuyo `next_due_date` ya ha llegado, y avanza su siguiente vencimiento (o los archiva, si no son recurrentes o han llegado a su `end_date`) — sin intervención de ningún usuario.

## 4. Endpoints

Prefijo de recurso: `/api/v1/accounts/{account_id}/payment-plans` — anidado bajo `accounts`, mismo criterio que `transactions.md` §4: un plan pertenece siempre a una cuenta concreta, así que no hay el dilema de `group_id` como query param que sí existe en `accounts`/`categories`.

### `POST /api/v1/accounts/{account_id}/payment-plans`

Requiere rol `owner` o `admin` en el grupo de la cuenta.

- **Entrada**: `type` (`income`/`expense`/`transfer`), `amount` (magnitud positiva), `category_id` (opcional, solo si `type` no es `transfer`), `to_account_id` (obligatorio si `type = transfer`, prohibido en el resto), `description` (opcional), `next_due_date`, `end_date` (opcional, solo si `is_recurring`), `is_recurring` (por defecto `false`), `frequency_interval`/`frequency_unit` (obligatorios si `is_recurring`, prohibidos si no).
- **Efecto**: crea el plan. No genera ninguna `transaction` todavía, aunque `next_due_date` ya haya pasado — eso es trabajo exclusivo del proceso diario (sección 5), nunca de este endpoint.
- **Salida**: el plan creado.
- **Errores**: `403` si el usuario no pertenece al grupo, o pertenece con rol `member`. `422` si la combinación `type`/`category_id`/`to_account_id` es inválida, si `is_recurring`/`frequency_interval`/`frequency_unit`/`end_date` son inconsistentes entre sí, o si `end_date` es anterior a `next_due_date`. `409` si `category_id` o `to_account_id` no pertenecen al mismo grupo que la cuenta, o si `to_account_id` coincide con `account_id`.

### `GET /api/v1/accounts/{account_id}/payment-plans`

Requiere pertenencia al grupo de la cuenta, cualquier rol.

- **Salida**: los planes de la cuenta (activos y archivados), envueltos en `{items: [...]}`, sin paginar — el volumen esperado por cuenta es pequeño (`ARCHITECTURE.md` §9.2), a diferencia del historial de `transactions`.
- **Errores**: `403` si no pertenece al grupo de la cuenta.

### `GET /api/v1/accounts/{account_id}/payment-plans/{payment_plan_id}`

Requiere pertenencia al grupo de la cuenta.

- **Salida**: el detalle del plan.
- **Errores**: `403` si no pertenece al grupo de la cuenta — nunca `404`. `404` si `payment_plan_id` no existe o pertenece a otra cuenta (mismo criterio que `transactions.md` §5 entre `account_id` y `transaction_id`).

### `PATCH /api/v1/accounts/{account_id}/payment-plans/{payment_plan_id}`

Requiere rol `owner` o `admin` en el grupo de la cuenta. Actualización parcial (`ARCHITECTURE.md` §5.5).

- **Entrada**: `amount`, `type`, `category_id`, `description`, `next_due_date`, `end_date`, `is_recurring`, `frequency_interval`, `frequency_unit`, `is_active` — todos opcionales. `type` solo admite alternar entre `income`/`expense` (mismo criterio que `transactions.md` §5); `account_id`/`to_account_id` no son editables.
- **Efecto**: `is_active = false` archiva el plan — deja de procesarlo el proceso diario, sin borrarlo. No existe borrado físico en v1.
- **Errores**: `400` si no se incluye ningún campo. `403`/`404` con el mismo criterio que el `GET` de detalle. `422` si `type = transfer`, o si la nueva combinación de `is_recurring`/`frequency_interval`/`frequency_unit`/`end_date` es inconsistente. `409` si se intenta cambiar el `type` de un plan que ya es `transfer`, o si el nuevo `category_id` no pertenece al grupo de la cuenta.

### `GET /api/v1/payment-plans/upcoming?group_id={group_id}&until={date}`

Requiere pertenencia al grupo, cualquier rol. **Router aparte**: el resto de endpoints de este dominio cuelgan de `/accounts/{account_id}/payment-plans`, pero este es de grupo (`ARCHITECTURE.md` §8.3), y un `APIRouter` solo admite un `prefix`. Se declara un segundo router con `prefix="/payment-plans"` en el mismo fichero, registrado aparte en `app/main.py`.

- **Entrada**: `group_id` (obligatorio, es el ámbito y resuelve la autorización), `until` (obligatorio, fecha límite inclusiva).
- **Salida**: los planes activos de cualquier cuenta del grupo con `next_due_date <= until`, ordenados por fecha, envueltos en `{items: [...]}`, sin paginar.
- **Sin cota inferior a propósito**: un plan con `next_due_date` ya pasada (porque el cron todavía no ha corrido hoy) es dinero que **aún tiene que salir**, así que cuenta como pendiente. Filtrar por `>= hoy` lo dejaría fuera y descuadraría cualquier previsión que use este endpoint.
- **Errores**: `403` si el usuario no pertenece a `group_id`.

## 5. Reglas de negocio

- `created_by` conserva quien creó el plan y `updated_by` quien realizó el último cambio humano, incluido archivarlo o reactivarlo mediante `PATCH`. Son referencias opcionales a `users` para preservar el histórico si se elimina una identidad.
- **Gestionar planes es gobierno del grupo**, igual que `accounts`/`categories`: crear, editar y archivar requiere `owner`/`admin`. A diferencia de una `transaction` puntual (anotar algo que ya pasó, fácil de corregir si se anota mal), un plan de pago automatiza movimientos futuros repetidos — un error aquí no se limita a una fila, se repite solo cada vez que el plan vence.
- **`amount` es siempre una magnitud positiva**, sin signo: a diferencia de `transactions`, un plan no es un movimiento real y no afecta a ningún `balance`, así que no necesita la partida doble ni la convención de signo de `transactions.md` §5 — el signo se resuelve cuando el plan se materializa, con la misma lógica que ya usa `POST /transactions`.
- **Estructura por `type`**, mismo criterio que `transactions.md` §5 (`transfer` exige `to_account_id` y prohíbe `category_id`; `income`/`expense` prohíben `to_account_id`), validado en el propio schema de entrada, no en `service.py`.
- **`category_id`/`to_account_id` deben pertenecer al mismo grupo que la cuenta** — `category_id` lo impone también un trigger de base de datos (`check_payment_plan_category_group`); `to_account_id` no tiene trigger equivalente (mismo hueco documentado en `transactions.md` §5), se valida solo en la aplicación.
- **Un plan recurrente necesita periodicidad; uno puntual no admite ninguna** — impuesto por `CHECK chk_recurring_fields`: `is_recurring = true` exige `frequency_interval`/`frequency_unit`; `is_recurring = false` los prohíbe, y prohíbe también `end_date` (fin de una repetición que no existe). `end_date`, cuando aplica, no puede ser anterior a `next_due_date` (`CHECK chk_end_date_after_due`).
- **Proceso diario de materialización** (fuera del ciclo petición/respuesta de la API, sin endpoint HTTP que lo dispare): un script (`app/payment_plans/run_due.py` o equivalente) se ejecuta una vez al día vía cron del sistema/contenedor — no un scheduler embebido en el proceso de FastAPI, coherente con `ARCHITECTURE.md` §9 (sin objetivo de alta disponibilidad, sin tráfico que justifique un proceso en segundo plano dentro de la API). Por cada plan activo con `next_due_date <= hoy`:
  1. Genera una `transaction` (o el par de filas, si `type = transfer`) mediante `TransactionService.create_transaction`, con `transactions.payment_plan_id` apuntando al plan. `created_by`/`updated_by` quedan `NULL`: ningún usuario ha actuado, lo hizo el proceso automático.
  2. Si `is_recurring`, avanza `next_due_date` sumándole `frequency_interval` unidades de `frequency_unit` **a partir de la fecha de vencimiento programada, no de la fecha real de ejecución** — para que un plan mensual del día 1 se mantenga en el día 1 aunque el cron se ejecute con retraso. Si la nueva fecha supera `end_date`, el plan se archiva (`is_active = false`) en vez de avanzar.
  3. Si no es recurrente, el plan se archiva tras generar su única transacción.
  4. Cada plan se procesa en su propia transacción de base de datos: si falla la generación de la `transaction`, no se avanza `next_due_date` ni se archiva el plan — el vencimiento queda pendiente para la siguiente ejecución, en vez de perderse.
- **Archivar la cuenta o el grupo suspende sus planes.** El proceso diario solo materializa planes cuya cuenta y cuyo grupo estén activos, además del propio `is_active` del plan. Sin esa condición, archivar —que es la forma de decir "esto ya no lo uso"— no detendría nada: el cron seguiría creando transacciones y moviendo el saldo de cuentas que el usuario dio por cerradas.
  - La suspensión es **reversible y no destructiva**: no toca el `is_active` del plan ni su `next_due_date`. Desarchivar la cuenta o el grupo lo reanuda tal como estaba.
  - Se comprueba en dos sitios: al seleccionar los planes vencidos y otra vez al procesar cada uno. No es redundancia — cada plan se materializa en su propia sesión, después de la consulta, así que archivar algo a mitad de ejecución tiene que quedar cubierto.
- **El "ancla de cobro" del grupo se deriva de estos planes, sin columna que lo marque.** Las vistas de previsión (`account_groups.md` §4) se organizan alrededor de cuándo entra el próximo ingreso periódico: de ahí salen los días restantes, el saldo real y el horizonte de la proyección. Ese plan es, por convención, **el plan activo del grupo con `type = 'income'` e `is_recurring = true` que tenga el `next_due_date` más próximo**, desempatando por `amount` descendente (si dos ingresos recurrentes caen el mismo día, la nómina es casi siempre el mayor).
  - Su `next_due_date` es la fecha de cobro y su `amount` lo que entra ese día. No hace falta aritmética de calendario en ninguna parte: el proceso diario ya mantiene `next_due_date` al día, incluido el ajuste de fin de mes.
  - Un grupo sin ningún plan que cumpla la convención **no es un error**: los endpoints que dependen del ancla devuelven `null` en los campos afectados y siguen sirviendo el resto.
  - Limitación conocida y asumida: cualquier ingreso recurrente con fecha más próxima que la nómina secuestra el ancla. Ver [ADR-0003](../decisions/0003-ancla-de-cobro-derivada.md), que documenta también la salida (una columna `is_payday`).
- **Los "gastos fijos pendientes" son solo los de `type = 'expense'`.** El plan que resulta ser el ancla se excluye por `id`, no por heurística — pero además, al filtrar por `expense`, tanto los ingresos como las transferencias quedan fuera de un plumazo.
- Igual que en el resto de dominios, un error de autorización nunca se enmascara como recurso inexistente: no pertenecer al grupo de la cuenta da `403`, nunca `404`; un `payment_plan_id` que no cuadra con `account_id` sí da `404`.
- El borrado es lógico solo en el sentido de `is_active`, igual que `accounts`/`categories`: no hay columna `deleted_at` en `payment_plans` (a diferencia de `transactions`, que sí es un registro histórico). Un plan archivado deja de procesarse, pero conserva sus datos y puede reactivarse con el mismo `PATCH`.

## 6. Fuera de alcance (v1)

- Recuperar automáticamente vencimientos atrasados si el cron deja de ejecutarse varios días seguidos — cada ejecución procesa como mucho un vencimiento por plan, no encadena varios aunque `next_due_date` siga estando en el pasado tras avanzarlo una vez.
- **Descartar los vencimientos ocurridos mientras la cuenta o el grupo estaban archivados.** Al suspender sin tocar `next_due_date` (ver §5), un plan mensual archivado tres meses conserva su vencimiento antiguo, y al desarchivar se pone al día a razón de uno por noche, generando transacciones con fecha pasada. Es coherente con el punto anterior —un cron caído se comporta igual— pero conviene saberlo: archivar no es lo mismo que cancelar. Para no arrastrar esos vencimientos, el plan se archiva por su cuenta (`is_active = false`).
- Endpoint HTTP para forzar manualmente la materialización de planes vencidos (útil para pruebas) — en v1 solo se dispara vía cron/script.
- Notificar al usuario antes de que un plan se materialice, o pedirle confirmación.
- Editar `account_id` o `to_account_id` de un plan ya creado, o cambiar `type` hacia/desde `transfer`.
- Historial de qué transacciones ha generado un plan a lo largo del tiempo más allá de lo que ya permite consultar `transactions.payment_plan_id` — no hay un endpoint dedicado tipo `GET /payment-plans/{id}/transactions`.
- Borrado físico de un plan — solo archivado (`is_active = false`).
- **Marcar explícitamente qué plan es el cobro que ancla el ciclo** (`is_payday`): se deriva por convención, con la limitación descrita en la sección 5.
- **Contar las transferencias programadas como gasto fijo pendiente.** Una transferencia automática de una cuenta gastable a una de ahorro **sí reduce el disponible**, aunque no reduzca el patrimonio; v1 no la cuenta, porque el filtro de pendientes se queda solo con `type = 'expense'`. Es una limitación conocida, no un olvido: contarla obligaría a decidir si la cuenta destino es gastable o no, caso por caso.
- **Previsión de importe variable**: `amount` es fijo. Un recibo de la luz que cambia cada mes se modela con su importe estimado y se corrige a mano.

## 7. Criterios de aceptación

- Crear un plan puntual (`is_recurring = false`) sin `frequency_interval`/`frequency_unit`/`end_date` funciona; incluir cualquiera de los tres devuelve `422`.
- Crear un plan recurrente sin `frequency_interval` o sin `frequency_unit` devuelve `422`.
- Crear un plan recurrente con `end_date` anterior a `next_due_date` devuelve `422`.
- Crear un plan `transfer` sin `to_account_id`, o con `category_id`, devuelve `422`.
- Crear un plan con `to_account_id` de otro grupo, o igual a `account_id`, devuelve `409`.
- El proceso diario, ejecutado sobre un plan puntual con `next_due_date` de hoy, genera una `transaction` con `payment_plan_id` apuntando al plan, y archiva el plan (`is_active = false`).
- El proceso diario, ejecutado sobre un plan mensual, genera la `transaction` y avanza `next_due_date` un mes exacto desde la fecha programada, no desde la fecha de ejecución.
- El proceso diario, ejecutado sobre un plan recurrente cuyo siguiente vencimiento superaría `end_date`, genera la última `transaction` y archiva el plan en vez de avanzar `next_due_date`.
- El proceso diario no toca los planes con `is_active = false` ni los que tienen `next_due_date` en el futuro.
- El proceso diario tampoco toca un plan cuya cuenta esté archivada, ni uno cuyo grupo lo esté, aunque el plan siga activo y vencido.
- Desarchivar la cuenta o el grupo reanuda sus planes con el mismo `next_due_date` que tenían: la suspensión no altera ningún dato del plan.
- Un `PATCH` sin ningún campo devuelve `400`, sin aplicar ningún cambio.
- Un miembro con rol `member` que intenta crear, editar o archivar un plan recibe `403`; consultar planes sí le funciona con cualquier rol.
- Un usuario sin pertenencia al grupo de la cuenta recibe `403` al operar sobre cualquiera de sus planes; un `payment_plan_id` que no pertenece a `account_id` devuelve `404`.
- `GET /payment-plans/upcoming` devuelve planes de **todas** las cuentas del grupo, no solo de una, ordenados por `next_due_date`.
- Un plan con `next_due_date` de ayer aparece en `upcoming`: sigue pendiente de materializarse.
- Un plan archivado (`is_active = false`) no aparece en `upcoming` aunque su fecha caiga dentro del rango.
- En un grupo con una nómina mensual (income, recurrente, día 5) y un alquiler mensual (expense, recurrente, día 1), el ancla de cobro es la nómina; añadir un segundo ingreso recurrente el día 2 hace que el ancla pase a ser ese ingreso (limitación conocida de la sección 5).
- En un grupo sin ningún ingreso recurrente activo, el ancla es `null` y los endpoints que dependen de ella no fallan.
