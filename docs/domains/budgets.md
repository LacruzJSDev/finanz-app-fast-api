# SPEC de dominio — budgets

## 1. Problema

Un grupo puede consultar cuánto lleva gastado por categoría (`transactions.md` §4.B), pero no tiene contra qué compararlo. "Llevas 380 € en Comida" no significa nada por sí solo: significa algo distinto según si el objetivo eran 300 € o 500 €.

Este dominio guarda ese objetivo —cuánto se pretende gastar al mes en cada categoría— para que el gasto real se pueda leer como "vas bien" o "te has pasado", y para que las gráficas tengan una línea de referencia.

## 2. Relación con otros dominios

Depende de `categories` (`category_id`, obligatorio) y de `users` (`created_by`/`updated_by`). No tiene columna `group_id`: se llega al grupo por `categories.group_id`, la misma decisión que toma `transactions` al llegar por `accounts`. Una columna denormalizada aquí exigiría un trigger solo para mantenerla coherente con la categoría.

Consume `transactions` para calcular el gasto real, pero **ese cálculo vive aquí**, no en `transactions.md` — igual que la materialización de un plan vencido vive en `payment_plans` aunque cree transacciones.

No depende de `accounts`: se presupuesta por categoría, no por cuenta. Un presupuesto de "Comida" cubre lo gastado en comida se pague con la tarjeta o en efectivo.

La autorización se reutiliza tal cual de `categories`: `RequireCategoryOwnerOrAdmin` y `RequireCategoryMembership` de `app/categories/dependencies.py`, más `RequireMembership` de `account_groups` para el listado por grupo. Este dominio no escribe ni una línea de autorización propia — es la ventaja de que la clave del path sea la categoría (ver sección 5).

## 3. Casos de uso

- Un miembro con rol `owner` o `admin` fija cuánto quiere gastar al mes en una categoría.
- Un miembro con rol `owner` o `admin` cambia ese importe a partir de un mes concreto, sin perder lo que había presupuestado antes.
- Un miembro con rol `owner` o `admin` deja de presupuestar una categoría, sin borrar el histórico.
- Un miembro, sea cual sea su rol, consulta los presupuestos vigentes de un mes junto a lo realmente gastado en cada uno.
- Un miembro consulta el histórico de un presupuesto: qué importe estuvo vigente en cada periodo.

## 4. Endpoints

Prefijo de recurso: `/api/v1/budgets`. Igual que `accounts` y `categories`, **no** anidado bajo otro dominio; el listado usa `group_id` como query param y los endpoints de escritura usan `category_id` como segmento de ruta.

### `PUT /api/v1/budgets/{category_id}`

Requiere rol `owner` o `admin` en el grupo de la categoría. **Idempotente**: la clave es la categoría, no una fila.

- **Entrada**: `amount` (entero positivo, céntimos), `valid_from` (opcional, por defecto el día 1 del mes en curso).
- **Efecto**: deja `amount` como presupuesto vigente de la categoría desde `valid_from`. Según el estado previo:

  | Situación | Efecto |
  |---|---|
  | La categoría no tiene presupuesto vigente | Crea la fila, con `valid_to` a `null`. |
  | Hay uno vigente y su `valid_from` es el mismo | Corrige el importe en esa fila, sin crear otra. |
  | Hay uno vigente con `valid_from` anterior | Lo cierra (`valid_to = valid_from` del nuevo) y crea la fila nueva. |
  | Hay uno vigente con `valid_from` posterior | `409` — retrodatar está fuera de alcance (sección 6). |

- **Salida**: el presupuesto vigente resultante.
- **Errores**: `403` si el usuario no pertenece al grupo de la categoría, o pertenece con rol `member`. `409` al intentar retrodatar, o si la categoría está archivada (`is_active = false`). `422` si `amount` no es positivo.

### `DELETE /api/v1/budgets/{category_id}`

Requiere rol `owner` o `admin` en el grupo de la categoría.

- **Efecto**: cierra el presupuesto vigente poniéndole `valid_to` a la fecha de hoy. Significa "dejar de presupuestar esta categoría", no "borrar lo que presupuesté": el histórico se conserva entero y sigue apareciendo en el endpoint de historial.
- **Salida**: `204 No Content`.
- **Errores**: `403` con el criterio de siempre. `404` si la categoría no tiene ningún presupuesto vigente — borrar dos veces devuelve `404` la segunda, no un `204` silencioso (mismo criterio que `transactions.md` §4).

### `GET /api/v1/budgets/{category_id}/history`

Requiere pertenencia al grupo de la categoría, cualquier rol.

- **Salida**: todos los periodos de esa categoría, vigentes y cerrados, ordenados por `valid_from` descendente, envueltos en `{items: [...]}`, sin paginar. El volumen esperado es de unas pocas filas por categoría.
- **Errores**: `403` si no pertenece al grupo de la categoría.

### `GET /api/v1/budgets?group_id={group_id}&month={date}`

Requiere pertenencia al grupo, cualquier rol. Es el endpoint que alimenta la pantalla de presupuestos.

- **Entrada**: `group_id` (obligatorio, es el ámbito), `month` (opcional, cualquier fecha del mes consultado; por defecto el mes en curso).
- **Salida**: `CollectionResponse[BudgetProgressRead]` — una fila por presupuesto vigente ese mes, con `category_id`, `category_name`, `parent_id`, `amount`, `spent`, `remaining` y `percentage`. `spent` es la magnitud gastada, positiva. Ordenado por nombre de categoría.
- **Errores**: `403` si el usuario no pertenece a `group_id`.

## 5. Reglas de negocio

- **Presupuestar es gobierno del grupo**, igual que `accounts` y `categories`: escribir exige `owner`/`admin`, leer le funciona a cualquier miembro. Un presupuesto no es una anotación cotidiana, es una decisión que afecta a cómo todo el grupo lee sus propios números.

- **Una fila por periodo de vigencia, no por mes.** Cambiar el importe cierra la fila vigente y abre otra; el histórico son los rangos. Nadie tiene que crear filas al empezar el mes, y un presupuesto estable durante dos años es una fila, no veinticuatro. El razonamiento completo y las alternativas descartadas están en [ADR-0005](../decisions/0005-presupuestos-plantilla-vigente.md).

- **El intervalo es semiabierto `[valid_from, valid_to)`.** El día que cierra una fila es exactamente el mismo que abre la siguiente: así no hay ni solape ni un hueco de un día entre periodos consecutivos, que es el error clásico de los rangos cerrados por ambos lados.

- **El presupuesto de un mes es el que estaba vigente el día 1 de ese mes.** Una fila con `[2026-03-15, null)` no aplica a marzo: aplica a abril en adelante. Es una convención, no una deducción — hacía falta elegir un instante de referencia y el día 1 es el único que no depende de cuándo se consulte.

- **No hay `PATCH`, hay `PUT` sobre la categoría.** El recurso que el usuario manipula es "el presupuesto de Comida", no "la fila con id X". Con `PATCH /budgets/{budget_id}` habría que explicar por qué cambiar `amount` unas veces modifica esa fila y otras crea una nueva: un contrato que miente sobre lo que hace. Como efecto lateral bueno, que la clave del path sea la categoría permite reutilizar `RequireCategoryOwnerOrAdmin` sin escribir autorización nueva.

- **El solape de periodos lo impide la base de datos, no solo el service.** Un `EXCLUDE USING gist` sobre `(category_id, daterange(valid_from, valid_to, '[)'))` rechaza cualquier par de filas de la misma categoría cuyos rangos se toquen. Un índice único parcial sobre `valid_to IS NULL` —la técnica que el proyecto ya usa en `uq_auth_providers_local_per_user`— garantizaría una sola fila vigente pero no cerraría la carrera entre dos peticiones concurrentes que leen la misma fila y ambas insertan. El `EXCLUDE` lo subsume: un rango abierto solapa con cualquier rango posterior.
  - Requiere la extensión `btree_gist`, **la primera del proyecto**. `CREATE EXTENSION` necesita rol privilegiado y producción usa el Postgres compartido del VPS: hay que verificarlo antes de escribir la migración. Plan B documentado en el ADR.
  - Una violación lanza `SQLSTATE 23P01`, que sin traducir saldría como `500`. Se cubre en dos capas: el service cierra la fila vigente antes de insertar, así el constraint solo dispara bajo carrera genuina, y un manejador de `IntegrityError` en `app/shared/error_handlers.py` lo traduce a `409`.

- **El gasto de una subcategoría cuenta contra el presupuesto de su categoría padre**, y aun así se puede presupuestar a cualquier nivel. Las dos reglas están en tensión y hay que resolverla con cuidado: si el gasto se agrupara ya por la categoría raíz, un presupuesto puesto sobre una subcategoría no casaría con ninguna clave y saldría siempre a cero. La consulta agrupa por la categoría propia de cada transacción y luego une por dos ramas — la categoría del presupuesto, o su padre.
  - **Consecuencia que hay que asumir**: si se presupuesta una raíz *y* una de sus hijas, el gasto de la hija cuenta en las dos filas. No es un error, es lo que significan las dos reglas juntas; la interfaz debe mostrarlas anidadas para que se entienda, no como dos líneas planas que no suman.
  - La jerarquía es de exactamente dos niveles (`trg_check_category_depth`), así que el rollup es un `COALESCE(parent_id, id)`, nunca una CTE recursiva.

- **El gasto real solo cuenta `type = 'expense'`**, y excluye las transacciones borradas lógicamente. Las transferencias quedan fuera por definición: un movimiento interno no consume presupuesto.

- **Un presupuesto de una categoría archivada no se puede crear ni modificar**, pero los que ya existan siguen apareciendo en el historial. Archivar una categoría no debe reescribir el pasado.

- **Los importes son enteros de céntimos**, como en todo el proyecto. `percentage` se calcula sobre ellos y se devuelve como entero (85 significa 85 %), para no introducir decimales en una API que hasta ahora no los tiene.

- Igual que en el resto de dominios, un error de autorización nunca se enmascara como recurso inexistente: no pertenecer al grupo de la categoría da `403`, nunca `404`.

## 6. Fuera de alcance (v1)

- **Metas de ahorro.** No pertenecen a este dominio ni existen en ninguno: se descartaron explícitamente del alcance del proyecto. Un presupuesto acota lo que sale; una meta persigue lo que se acumula, y modelarlo bien exige decidir si el progreso es el saldo de una cuenta, una suma de aportaciones propias o una categoría — una decisión que no se ha tomado.
- **Retrodatar un presupuesto**: un `valid_from` anterior al de la fila vigente devuelve `409`. Recomponer el histórico hacia atrás exigiría partir periodos ya cerrados.
- **Presupuestos por cuenta o por tipo de cuenta**: solo por categoría.
- **Presupuestos de ingreso** ("quiero ingresar al menos X"): solo se presupuesta gasto.
- **Periodos distintos del mes**: semanal, trimestral o anual. La vigencia es un rango de fechas arbitrario, pero la comparación con el gasto siempre se hace mes a mes.
- **Alertas o notificaciones** al superar un presupuesto: el endpoint devuelve el porcentaje, quien decide qué hacer con él es el cliente.
- **Arrastrar el sobrante** de un mes al siguiente.
- **Presupuesto total del grupo** como concepto propio, distinto de la suma de los de sus categorías.
- **Borrado físico** de un periodo ya cerrado.

## 7. Criterios de aceptación

- `PUT` sobre una categoría sin presupuesto crea una fila con `valid_to` nulo y el `valid_from` del día 1 del mes en curso si no se envía.
- `PUT` dos veces el mismo día con importes distintos deja **una sola fila**, con el segundo importe: no se abre un periodo de longitud cero.
- `PUT` con un `valid_from` posterior al de la fila vigente deja **dos filas**, y el `valid_to` de la primera es exactamente el `valid_from` de la segunda — sin solape ni hueco.
- `PUT` con un `valid_from` anterior al de la fila vigente devuelve `409`, sin tocar ninguna fila.
- `PUT` con `amount` cero o negativo devuelve `422`.
- `DELETE` cierra la fila vigente con `valid_to` de hoy y devuelve `204`; repetirlo devuelve `404`, y el historial sigue mostrando el periodo cerrado.
- `GET /budgets?group_id=&month=` de un mes anterior a un cambio de importe devuelve el importe **antiguo**, no el vigente hoy.
- Un presupuesto que empezó a mitad de mes no aparece como presupuesto de ese mes, sino del siguiente.
- Un presupuesto sobre una categoría raíz refleja en `spent` también lo gastado en sus subcategorías.
- Un presupuesto sobre una subcategoría refleja en `spent` solo lo suyo, no lo de su padre ni lo de sus hermanas.
- Presupuestar a la vez una raíz y una de sus hijas hace que el gasto de la hija aparezca contado en las dos filas.
- Una transferencia entre dos cuentas del grupo no aparece en `spent` de ningún presupuesto.
- Una transacción borrada lógicamente deja de contar en `spent` inmediatamente.
- Una categoría con presupuesto y sin ningún gasto devuelve `spent = 0` y `percentage = 0`, no `null`.
- Un miembro con rol `member` que intenta fijar o cerrar un presupuesto recibe `403`; consultarlos sí le funciona con cualquier rol.

> Los criterios que dependen de agregación —el rollup, la exclusión de transferencias y borradas, y el `EXCLUDE` de solapes— **se verifican a mano contra la base de datos real**. Los tests unitarios sustituyen el repositorio por un `MagicMock`, así que ese SQL nunca llega a ejecutarse en ellos (`ARCHITECTURE.md` §10). Lo que sí es testeable unitariamente son las cuatro ramas de la lógica del `PUT`.
