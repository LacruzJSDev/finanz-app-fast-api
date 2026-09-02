# ARCHITECTURE — Backend de FinanzApp

## 1. Resumen

Este documento define las decisiones de arquitectura transversales del backend de FinanzApp: organización del código, patrones de acceso a datos, convenciones de API, gestión de la sesión de base de datos, autenticación y autorización.

No contiene reglas de negocio específicas de un dominio (por ejemplo, la matriz de permisos por rol, el flujo de invitaciones, o el comportamiento de conversión de un plan de pago en una transacción real). Esas decisiones se documentan en un SPEC independiente por dominio, referenciado en la sección 12.

Repositorio: `finanz-app-fast-api`.

---

## 2. Principios de arquitectura

### 2.1 Organización del código: vertical slicing por dominio

El proyecto se organiza por dominio funcional, no por capa técnica. Cada dominio es una carpeta autocontenida:

```
finanz-app-fast-api/
├── alembic/
│   ├── env.py
│   ├── script.py.mako
│   └── versions/
├── alembic.ini
├── app/
│   ├── config.py
│   ├── database.py
│   ├── db_registry.py
│   ├── main.py
│   ├── users/
│   ├── auth/
│   ├── account_groups/
│   ├── accounts/
│   ├── categories/
│   ├── payment_plans/
│   ├── transactions/
│   └── shared/
│       ├── dependencies.py
│       └── exceptions.py
└── tests/
```

Se permiten y se esperan referencias cruzadas entre dominios cuando existe una relación de dependencia real en el modelo de datos (por ejemplo, `transactions` referencia `Account`; `auth` referencia `User`). No se busca aislamiento total entre dominios, sino una propiedad clara de cada uno sobre su propia lógica.

### 2.2 Separación de responsabilidades por capa (Router–Service–Repository)

Dentro de cada dominio:

| Capa | Responsabilidad | No debe contener |
|---|---|---|
| `router.py` | Presentación HTTP: define endpoints, delega en `service` | Lógica de negocio, acceso a datos |
| `service.py` | Lógica de negocio, orquestación de repositorios | Referencias a FastAPI o al protocolo HTTP |
| `repository.py` | Acceso a datos vía ORM | Lógica de negocio, gestión de transacciones (`commit`/`rollback`) |
| `models.py` | Modelos ORM, mapeo del esquema relacional | — |
| `schemas.py` | Validación y serialización de peticiones/respuestas | — |

La dirección de dependencia es única: `router → service → repository`. Una capa nunca depende de una capa que la contiene.

### 2.3 Entrada a los métodos de `service.py`

Un método de servicio nunca recibe el schema de Pydantic de la petición (`RegisterRequest`, etc.) como parámetro, aunque no sea en sí mismo un objeto de FastAPI: acoplaría el service a las reglas de validación de una petición HTTP concreta, y le impediría llamarse desde cualquier sitio que no sea ese endpoint (un script, un test, otro flujo que reutilice la misma lógica).

Hasta tres parámetros, van sueltos y tipados (`email: str, name: str, password: str`). A partir de ahí, o cuando el mismo grupo de campos vaya a viajar por varias capas, se agrupan en un `@dataclass` propio del service — un "comando" — nunca en el schema de entrada:

```python
@dataclass
class RegisterCommand:
    email: str
    name: str
    password: str

class AuthService:
    def register(self, command: RegisterCommand) -> AuthResult: ...
```

Es la misma idea que ya se aplica a la salida: los métodos de servicio devuelven un tipo propio (`AuthResult`, no `LoginResponse`) por la misma razón. El router es quien traduce entre el schema de la petición y el comando del service — esa traducción es precisamente su trabajo.

---

## 3. Gestión de la sesión de base de datos

Cada petición HTTP obtiene una sesión de base de datos independiente mediante inyección de dependencias. La confirmación de cambios (`commit`) ocurre una única vez, al final de la petición; cualquier excepción no controlada revierte la totalidad de los cambios de esa petición:

```python
def get_db():
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
```

La capa de repositorio no confirma transacciones de forma independiente. La unidad de trabajo coincide con el ciclo de vida completo de la petición, garantizando que operaciones con múltiples escrituras relacionadas (por ejemplo, una transacción financiera y la actualización de saldo derivada mediante trigger) se confirmen o reviertan como un conjunto atómico.

---

## 4. Configuración

La configuración de la aplicación se centraliza en `app/config.py`, mediante un objeto `Settings` construido a partir de variables de entorno en el momento del arranque. Ningún otro módulo lee variables de entorno directamente.

Variables de entorno esperadas:

| Variable | Propósito |
|---|---|
| `DATABASE_URL` | Cadena de conexión a PostgreSQL |
| `SECRET_KEY` | Clave de firma de los JWT |
| `JWT_ALGORITHM` | Algoritmo de firma (HMAC simétrico por defecto) |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | Duración del token de acceso |
| `JWT_REFRESH_TOKEN_EXPIRE_DAYS` | Duración del refresh token |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | Credenciales OAuth 2.0 para el proveedor Google |
| `CORS_ALLOWED_ORIGINS` | Orígenes permitidos para peticiones cross-origin; obligatorio en producción y solo orígenes HTTPS exactos separados por comas |
| `ENVIRONMENT` | Entorno de ejecución (`development` / `production`); cualquier otro valor impide arrancar |

Los valores por defecto de desarrollo se cargan desde un fichero `.env` no versionado. La aplicación no debe arrancar si falta una variable obligatoria. En producción también falla si `SECRET_KEY` tiene menos de 32 caracteres, si no hay orígenes CORS, si se repiten, si incluyen `*` o si no son orígenes HTTPS exactos (sin ruta, query ni fragmento).

---

## 5. Convenciones de API

### 5.1 Versionado

Todas las rutas se exponen bajo el prefijo `/api/v1`. Un cambio incompatible en el contrato de un endpoint existente requiere una nueva versión de prefijo, no una modificación in place.

### 5.2 Identificadores

Las claves primarias son UUID v4, generadas a nivel de base de datos (`gen_random_uuid()`). Se serializan como cadena de texto en las respuestas JSON.

### 5.3 Fechas y horas

Las marcas de tiempo (`created_at`, `updated_at`) se almacenan y sirven en UTC, serializadas en formato ISO 8601. Las fechas sin componente horario (`transactions.date`) representan la fecha del movimiento tal como la registra el usuario, independiente de zona horaria, por diseño.

### 5.4 Colecciones y paginación

**Ninguna colección se devuelve como array plano.** Toda respuesta de lista va envuelta en un objeto con la clave `items`, pagine o no. El cliente lee siempre `.items` sin tener que recordar qué endpoints paginan, y el envoltorio deja sitio para añadir metadatos más adelante sin romper el contrato.

Colección sin paginar — el caso general:

```json
{
  "items": [...]
}
```

Colección paginada — añade los metadatos sobre la misma estructura:

```json
{
  "items": [...],
  "total": 142,
  "limit": 20,
  "offset": 0
}
```

La paginación se implementa mediante `limit`/`offset`, apoyada en índices sobre la columna de ordenación relevante. Se aplica donde el volumen esperado lo justifica (ver sección 9). Los únicos endpoints paginados son los listados de transacciones —el anidado por cuenta y el plano por grupo (ver sección 8.3)—; el resto de colecciones son de tamaño naturalmente acotado.

Ambas formas están implementadas como esquemas genéricos reutilizables en `app/shared/schemas.py`, y se declaran como tipo de retorno del endpoint:

```python
def listar_grupos(...) -> CollectionResponse[AccountGroupRead]: ...
def listar_transacciones(...) -> PaginatedResponse[TransactionRead]: ...
```

### 5.5 Actualizaciones parciales

Los esquemas de actualización (`XUpdate`) declaran todos los campos como opcionales. Solo se aplican al recurso los campos presentes explícitamente en el cuerpo de la petición; un campo ausente no se modifica, y un campo enviado como nulo se aplica como tal cuando el modelo lo permite.

### 5.6 Convención de errores

#### Forma de la respuesta

**Todos** los errores de la API comparten una única estructura, sea cual sea su origen: validación, autorización, recurso inexistente, ruta mal escrita o fallo interno. El cliente puede escribir un solo manejador.

```json
{
  "error": {
    "code": "account_not_found",
    "message": "Cuenta no encontrada"
  }
}
```

- `code` — identificador estable, en `snake_case`, pensado para que el cliente distinga causas **sin leer el mensaje**. Es lo que se compara en un `switch`; el texto puede cambiar o traducirse sin romper nada.
- `message` — descripción legible para una persona.
- `details` — presente **solo** en errores de validación. Se omite del JSON cuando no aplica, nunca se envía como `null`.

Errores de validación (`422`), con el detalle por campo:

```json
{
  "error": {
    "code": "validation_error",
    "message": "Los datos enviados no son válidos",
    "details": [
      { "field": "body.email", "message": "Field required" },
      { "field": "body.amount", "message": "Input should be a valid integer" }
    ]
  }
}
```

`field` es la ruta del campo aplanada con puntos, empezando por su ubicación (`body`, `query`, `path`).

Esta forma **no** es la que FastAPI produce por defecto — sin intervención devolvería `detail` como lista en los `422`, `detail` como cadena en los `404` y texto plano sin JSON en los `500`. La unificación la hacen los manejadores registrados en `app/shared/error_handlers.py`.

#### Códigos de estado

| Código | Uso |
|---|---|
| `400` | Petición malformada que no es un fallo de esquema |
| `401` | Autenticación ausente o inválida |
| `403` | Autenticado, sin autorización sobre el recurso |
| `404` | Recurso inexistente |
| `409` | Conflicto de unicidad o de estado (por ejemplo, email ya registrado) |
| `422` | Error de validación de esquema de entrada |
| `500` | Error no controlado |

Un error de autorización nunca se enmascara como `404`.

Cuando PostgreSQL detecta una restricción antes que la comprobación de aplicación —por ejemplo, por una carrera entre dos peticiones— los SQLSTATE conocidos de unicidad, clave foránea, `CHECK`/trigger y exclusión se traducen también a `409` con este mismo contrato. No se expone el texto del motor ni el nombre de la restricción; un error de base de datos desconocido sigue siendo `500` y se registra para investigarlo.

#### Cómo se lanzan

La capa de servicio lanza excepciones de dominio, nunca `HTTPException`: así `service.py` no necesita conocer FastAPI ni los códigos HTTP (ver sección 2.2). La jerarquía base vive en `app/shared/exceptions.py`, y cada dominio deriva las suyas con un `code` propio:

```python
class InvalidCredentialsError(UnauthorizedError):
    code = "invalid_credentials"
    message = "Email o contraseña incorrectos"
```

La traducción de excepción a respuesta HTTP ocurre en un único sitio, el manejador global. Ningún router captura excepciones para convertirlas en respuestas.

#### Errores internos

Un `500` nunca expone la excepción original. El traceback completo va al log del servidor; el cliente recibe siempre el mismo cuerpo genérico, para no filtrar rutas de ficheros ni detalles de implementación a quien provoque el fallo.

### 5.7 CORS

Frontend y backend viven en orígenes distintos — no es un despliegue de mismo origen con rutas `/api` — pero en producción son el mismo **site**: `https://finanzapp.entramaes.com` y `https://api.finanzapp.entramaes.com` comparten dominio registrable y esquema HTTPS. La distinción importa: CORS sigue siendo necesario por ser cross-origin, mientras que `SameSite=Lax` sí permite las cookies entre ambos.

- Los orígenes permitidos se configuran mediante `CORS_ALLOWED_ORIGINS`, como lista explícita. En producción deben ser HTTPS, sin ruta, y no se permite el comodín (`*`).
- El middleware de CORS se registra con `allow_credentials=True`, imprescindible para que el navegador adjunte cookies en peticiones entre orígenes.
- El cliente debe emitir sus peticiones con `credentials: "include"` (o el equivalente de su librería HTTP); sin eso, el navegador no manda la cookie aunque el origen esté permitido.
- Toda mutación (`POST`, `PUT`, `PATCH`, `DELETE`) que lleve `access_token` o `refresh_token` exige además una cabecera `Origin` exactamente incluida en `CORS_ALLOWED_ORIGINS`. Si falta o no coincide responde `403` con el contrato de error común. Es la defensa CSRF elegida para cookies httpOnly; registro y login no llevan una cookie previa y no quedan bloqueados por ella.
- `GET`, `HEAD` y `OPTIONS` son siempre operaciones sin efectos. Una ruta nueva que cambie estado debe usar uno de los métodos mutantes anteriores; de lo contrario evitaría la validación de origen.

### 5.8 Endpoint de estado

`GET /health` expone el estado de disponibilidad del servicio, sin autenticación ni lógica de negocio, para verificación de despliegue.

---

## 6. Modelo de datos — mapa de referencia

El esquema relacional completo vive versionado mediante migraciones (Alembic) y no se duplica en este documento. Mapa de alto nivel:

> El diseño de referencia del esquema completo — todas las tablas, enums, triggers y funciones, con el razonamiento de cada decisión — está en [`docs/schema-reference.sql`](schema-reference.sql). Ese fichero **no se ejecuta nunca**: es documentación. Las tablas se van trasladando de allí a migraciones de Alembic a medida que se implementa cada dominio, y el propio fichero lleva el registro de qué está ya migrado.

| Entidad | Rol en el sistema |
|---|---|
| `users` | Identidad del usuario |
| `auth_providers` | Métodos de autenticación vinculados a un usuario |
| `sessions` | Sesiones activas, revocables |
| `account_groups` | Unidad de agrupación de cuentas, compartible entre usuarios |
| `account_group_members` | Pertenencia usuario–grupo con rol asociado |
| `invitations` | Ciclo de vida de invitaciones a un grupo |
| `accounts` | Cuentas financieras; saldo derivado y mantenido por trigger |
| `categories` | Clasificación jerárquica de transacciones |
| `payment_plans` | Movimientos futuros o recurrentes |
| `transactions` | Registro histórico de movimientos |
| `budgets` | Presupuesto mensual por categoría, vigente por rango de fechas |

**Divisa:** se ha decidido una única divisa por grupo de cuentas para el alcance actual, con `currency` manteniéndose como campo por cuenta (`accounts.currency`) en lugar de moverse a `account_groups` — se prevé que un grupo pueda admitir divisas distintas más adelante, y mantener el campo a nivel de cuenta evita una migración de esquema cuando eso ocurra. La coherencia (todas las cuentas de un mismo grupo en la misma divisa) se impone a nivel de aplicación y de interfaz, no mediante una restricción de base de datos. La validación concreta se define en `docs/domains/accounts.md` §5: la primera cuenta activa de un grupo fija su divisa, y cualquier cuenta posterior con una `currency` distinta se rechaza con `409`.

Las invariantes de negocio no expresables mediante claves foráneas simples (jerarquía de categorías, consistencia categoría–cuenta–grupo, cálculo de saldo) se implementan como triggers y funciones a nivel de base de datos.

---

## 7. Autenticación y autorización

### 7.1 Mecanismo

Autenticación basada en JSON Web Tokens, con soporte de múltiples proveedores de identidad desde el diseño inicial: credenciales locales (hash mediante bcrypt) y OAuth 2.0 (Google). La identidad (`users`) y el método de autenticación (`auth_providers`) están modelados por separado, permitiendo múltiples métodos por usuario.

La renovación de sesión se gestiona mediante refresh tokens; se persiste su hash, nunca el valor en claro, permitiendo revocación selectiva. Cada rotación consume la sesión mediante un `UPDATE` condicionado por hash, revocación y expiración, de modo que dos solicitudes concurrentes no pueden emitir dos sesiones desde el mismo token.

Ningún token viaja en el cuerpo de una respuesta ni en la cabecera `Authorization`: los endpoints que autentican (`register`, `login`, `google`, `refresh`) los entregan como cookies `httpOnly` — inaccesibles desde JavaScript, lo que cierra la vía más común de robo de tokens vía XSS. Duración, nombres, `Path` y el resto de atributos de cada cookie están documentados en `docs/domains/auth.md` §5, junto con la configuración de CORS que hace falta porque frontend y backend son dominios distintos (ver §5.7).

### 7.2 Control de acceso

Resuelto mediante inyección de dependencias encadenadas:

- **`get_current_user`** — valida el JWT y resuelve el usuario autenticado. Lo lee de la cookie `access_token`, no de una cabecera `Authorization`. Dependencia base de la que dependen las siguientes.
- **`verify_group_membership`** — para endpoints donde el identificador de grupo forma parte de la ruta.
- **`verify_account_access`** — para endpoints que operan sobre un recurso por su propio identificador, resolviendo la pertenencia al grupo antes de autorizar.

Las mutaciones de membresías que puedan retirar o degradar un `owner` (`PATCH` y `DELETE` de miembros) vuelven a leer todas las pertenencias con `SELECT ... FOR UPDATE`, ordenadas por identificador, dentro de la transacción de la petición. La comprobación de que queda al menos un `owner` y el cambio se ejecutan así sobre la misma fotografía bloqueada, evitando que dos peticiones concurrentes dejen el grupo sin propietario. Un objetivo que no sea miembro se trata como `404`; la autorización del solicitante no cambia.

Las relaciones que no pueden expresarse con una clave foránea simple se mantienen también en PostgreSQL: los triggers de categorías y los de transferencias/planes de transferencia verifican que las cuentas y categorías relacionadas estén dentro del mismo grupo. La validación de aplicación se conserva para traducir el caso esperado a `409`, pero no es la única barrera de integridad.

### 7.3 Separación entre identidad y autenticación

El dominio `users` gestiona el perfil (`GET /me`, `PATCH /me`) de forma independiente del dominio `auth`, que gestiona exclusivamente el ciclo de autenticación (`POST /auth/login`, `POST /auth/google`, `POST /auth/refresh`, `POST /auth/logout`).

---

## 8. Patrones de acceso a datos

### 8.1 Transacciones financieras

El acceso **al detalle** de una transacción —crearla, leerla, editarla, borrarla— ocurre siempre en el contexto de una cuenta específica (`/api/v1/accounts/{account_id}/transactions/{transaction_id}`). Una transacción pertenece a una cuenta y solo a una, incluidas las dos patas de una transferencia.

**Consultar y agregar, en cambio, ocurre en el ámbito del grupo** (ver sección 8.3). La redacción anterior de esta sección prohibía agregar las cuentas de un grupo en una sola consulta; esa decisión se revisó al implementar las vistas de estadísticas — el razonamiento completo, incluidas las alternativas descartadas, está en [ADR-0001](decisions/0001-agregados-por-grupo.md).

El saldo agregado de un grupo es la suma de los saldos ya derivados de sus cuentas — operación válida gracias a la restricción de divisa única por grupo (ver sección 6).

### 8.2 Borrado

El borrado físico es la convención por defecto. El borrado lógico (columna `deleted_at`) es una excepción justificada por dominio, no un patrón transversal — actualmente aplica solo a `transactions`, por razón de integridad del histórico contable. Su comportamiento exacto (incluida la corrección del saldo derivado) se define en el SPEC del dominio `transactions`.

### 8.3 Consultas: ámbito, filtros y agregados

Esta sección fija la política común de todo endpoint que consulta o agrega. Nace con `transactions`, pero aplica a cualquier dominio que en el futuro necesite lo mismo.

#### Ámbito

**El ámbito de toda consulta es el grupo, expresado como `group_id` en query param.** No es un filtro más: es lo que delimita a qué datos se tiene acceso, y es lo que resuelve la autorización (`RequireMembership`). Nunca se acepta una consulta sin ámbito.

**Restringir a una cuenta es un filtro, no un ámbito distinto.** `account_id` viaja como un query param más, al mismo nivel que `category_id` o `type`. Esto es deliberado: la interfaz muestra estadísticas tanto de una cuenta como de todo el grupo, y con este diseño ambas vistas son el mismo endpoint con un parámetro de diferencia, en vez de dos familias de endpoints que hay que mantener en paralelo.

Como consecuencia, autorizar por grupo y filtrar por cuenta obliga a una validación explícita: **la cuenta pedida debe pertenecer al grupo autorizado**. Sin ella, un miembro legítimo de un grupo podría leer movimientos de otro pasando un `account_id` ajeno. Es una comprobación de aplicación, en `service.py`, y devuelve `409` — no hay invariante de base de datos que la cubra.

Los endpoints de consulta viven en un router plano propio del dominio (`/api/v1/transactions`), separado del router anidado que sirve el CRUD (`/api/v1/accounts/{account_id}/transactions`). Ver [ADR-0002](decisions/0002-router-plano-de-consulta.md).

#### Filtros

**El mismo conjunto de filtros lo comparten el listado y sus agregados.** Un resumen describe exactamente las mismas filas que devolvería el listado con esos mismos parámetros; si divergieran, el usuario vería un total que no cuadra con lo que tiene delante. En la práctica esto significa un único constructor de condiciones reutilizado por ambas consultas, no dos listas de `where` mantenidas a mano.

Reglas transversales:

- Todo filtro es **opcional**; ausente significa "no restringe". El único parámetro obligatorio es el ámbito.
- Un filtro sobre una **categoría raíz incluye sus subcategorías**, y uno sobre una subcategoría devuelve solo la suya. La jerarquía es de exactamente dos niveles (impuesta por `trg_check_category_depth`), así que nunca hace falta una CTE recursiva. La condición es `COALESCE(parent_id, id) = :cat OR id = :cat`: el `COALESCE` por sí solo agrupa bien pero **filtra mal**, porque para una subcategoría devuelve el id del padre, no el suyo.
- La **búsqueda de texto** es `ILIKE '%término%'`, sin índice. A los volúmenes de la sección 9 es instantánea; si dejara de serlo, la salida es `pg_trgm` con índice GIN, no rediseñar el contrato.
- Los filtros **no cambian las reglas de visibilidad**: una transacción borrada lógicamente sigue sin aparecer, se filtre por lo que se filtre.

#### Agregados

- Todo agregado sobre transacciones excluye `deleted_at IS NOT NULL`.
- Cuando un agregado **reparte entre ingreso y gasto**, excluye además `type = 'transfer'`: un movimiento interno no es ninguna de las dos cosas. Sumaría cero al total, pero ensuciaría el desglose con una fila por cada cuenta implicada.
- `transactions` no tiene columna `group_id`. Todo agregado llega al grupo con `JOIN accounts ON accounts.id = transactions.account_id`.
- Un agregado vive en **el dominio dueño del dato**, no en un dominio transversal tipo `dashboard`: el saldo agregado en `accounts`, el desglose por categoría en `transactions`, los vencimientos en `payment_plans`.
- `GET /account-groups/{group_id}/overview` es la excepción de composición: reúne agregados de varios dominios en una respuesta para que una pantalla entera se calcule contra el mismo instante. Reutiliza los services de esos dominios, no reimplementa sus consultas.

#### Detalles de SQL agregado

Tres cosas que no tienen precedente en el resto del proyecto y son fuente de errores silenciosos:

1. **`func.sum` sobre una columna `BIGINT` devuelve `NUMERIC`**, y psycopg lo entrega como `Decimal`, no como `int`. El repositorio castea explícitamente antes de devolver; si no, el tipo declarado miente y pyright no lo detecta.
2. **`SUM` de cero filas es `NULL`, no `0`.** Siempre `func.coalesce(func.sum(...), 0)`.
3. **`func.sum(x).filter(cond)`** renderiza `SUM(x) FILTER (WHERE cond)`, y permite obtener varias sumas distintas en un solo escaneo de la tabla en vez de encadenar consultas.

Sobre índices: no se añade ninguno de forma preventiva. La sección 9 fija un supuesto de volumen bajo, y los índices existentes cubren los filtros que mandan. Cualquier índice nuevo se justifica midiendo, en su propio commit.

---

## 9. Supuestos no funcionales

- **Volumen de uso**: uso personal o de grupo reducido, no tráfico concurrente de escala SaaS. Justifica la elección de paginación por desplazamiento sobre paginación por cursor, de una única instancia de base de datos sin réplicas de lectura, y de calcular los agregados de la sección 8.3 en caliente en vez de precalcularlos.
- **Disponibilidad**: sin objetivo de alta disponibilidad definido para el alcance actual. Es lo que justifica que el proceso diario de `payment_plans` sea un cron del contenedor y no un planificador embebido en el proceso de FastAPI.
- **Observabilidad**: los logs se emiten a `stdout` en JSON cuando `ENVIRONMENT=production` y en texto coloreado en desarrollo (`app/logging_config.py`). En producción los recoge Grafana Alloy y los envía a Loki sin parseo, de ahí que el formato sea JSON: permite filtrar por campo en vez de buscar texto suelto. Los fallos de materialización de planes incluyen `event` y `payment_plan_id`, de modo que una regla de alertas puede distinguirlos de un error genérico. No hay trazabilidad distribuida ni correlación de peticiones.

---

## 10. Estrategia de pruebas

La separación `service`/`repository` permite pruebas unitarias rápidas de la
lógica de negocio, sustituyendo el repositorio por un doble de prueba, sin
infraestructura de persistencia real.

Las pruebas marcadas como `integration` ejercitan la aplicación con un
PostgreSQL real. Antes de la primera prueba aplican `alembic upgrade head` y
vacían todas las tablas entre casos mediante `TRUNCATE ... CASCADE`. El
entorno se activa solo al definir `TEST_DATABASE_URL`; esta URL debe apuntar a
una base cuyo nombre termine en `_test` y coincidir con `DATABASE_URL`. Es una
barrera deliberada contra borrar datos de desarrollo por error.

El CI crea `finanzapp_test` como servicio efímero de PostgreSQL y ejecuta
ambas suites. Por ello, una migración nueva debe tener al menos una prueba de
integración cuando su corrección dependa de PostgreSQL (triggers,
restricciones, índices, concurrencia o SQL específico), además de las
pruebas unitarias de la regla de negocio.

---

## 11. Fuera de alcance (transversal)

- Internacionalización de mensajes de error.
- Rate limiting.
- Trazabilidad distribuida y correlación de peticiones (el logging estructurado sí está, ver sección 9).
- Alta disponibilidad y réplicas de base de datos.
- Métricas y alertas: se recogen logs, pero no hay métricas de aplicación ni umbrales definidos.

---

## 12. Documentos relacionados

Las reglas de negocio específicas de cada dominio (endpoints concretos, casos de uso, criterios de aceptación, comportamiento de estado) se documentan en un SPEC independiente por dominio, no en este documento:

- `docs/domains/users.md`
- `docs/domains/auth.md`
- `docs/domains/account_groups.md`
- `docs/domains/accounts.md`
- `docs/domains/categories.md`
- `docs/domains/payment_plans.md`
- `docs/domains/transactions.md`
- `docs/domains/budgets.md`

Cada uno se redacta inmediatamente antes de comenzar la implementación del dominio correspondiente, no de forma anticipada para todos a la vez.

Además:

- `docs/schema-reference.sql` — diseño de referencia del esquema relacional completo (documentación, no ejecutable).
- `docs/decisions/` — registros de decisión (ADR). Este documento refleja el **estado vigente**: se reescribe cuando una decisión cambia, así que no conserva el razonamiento de lo descartado. Los ADR guardan esa historia, uno por decisión que invierte algo ya documentado, que no es evidente a partir del código, o que asume un riesgo conocido a cambio de simplicidad.

---

## 13. Mantenimiento del documento

Este documento refleja el estado vigente de las decisiones de arquitectura transversal. Se actualiza cuando una decisión de este nivel cambia; las decisiones de negocio por dominio se mantienen en sus propios documentos.
