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
| `CORS_ALLOWED_ORIGINS` | Orígenes permitidos para peticiones cross-origin |
| `ENVIRONMENT` | Entorno de ejecución (`development` / `production`) |

Los valores por defecto de desarrollo se cargan desde un fichero `.env` no versionado. La aplicación no debe arrancar si falta una variable obligatoria.

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

La paginación se implementa mediante `limit`/`offset`, apoyada en índices sobre la columna de ordenación relevante. Se aplica donde el volumen esperado lo justifica (ver sección 9.2). En el alcance actual, el único endpoint paginado es el listado de transacciones de una cuenta; el resto de colecciones son de tamaño naturalmente acotado.

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

Frontend y backend viven en dominios distintos — no es un despliegue de mismo dominio con rutas `/api`, sino dos orígenes separados de verdad. Como la sesión viaja en cookies (ver §7.1), esto son peticiones cross-site, no solo cross-origin, y eso condiciona toda la configuración:

- Los orígenes permitidos se configuran mediante `CORS_ALLOWED_ORIGINS`, como lista explícita. No se permite el origen comodín (`*`): un navegador lo rechaza en cuanto la petición lleva credenciales (cookies), así que con `*` las peticiones cross-site fallarían igualmente.
- El middleware de CORS se registra con `allow_credentials=True`, imprescindible para que el navegador adjunte cookies en peticiones entre orígenes.
- El cliente debe emitir sus peticiones con `credentials: "include"` (o el equivalente de su librería HTTP); sin eso, el navegador no manda la cookie aunque el origen esté permitido.

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

**Divisa:** se ha decidido una única divisa por grupo de cuentas para el alcance actual, con `currency` manteniéndose como campo por cuenta (`accounts.currency`) en lugar de moverse a `account_groups` — se prevé que un grupo pueda admitir divisas distintas más adelante, y mantener el campo a nivel de cuenta evita una migración de esquema cuando eso ocurra. La coherencia (todas las cuentas de un mismo grupo en la misma divisa) se impone a nivel de aplicación y de interfaz, no mediante una restricción de base de datos. La validación concreta se define en el SPEC del dominio `account_groups`/`accounts`, pendiente de redactar.

Las invariantes de negocio no expresables mediante claves foráneas simples (jerarquía de categorías, consistencia categoría–cuenta–grupo, cálculo de saldo) se implementan como triggers y funciones a nivel de base de datos.

---

## 7. Autenticación y autorización

### 7.1 Mecanismo

Autenticación basada en JSON Web Tokens, con soporte de múltiples proveedores de identidad desde el diseño inicial: credenciales locales (hash mediante bcrypt) y OAuth 2.0 (Google). La identidad (`users`) y el método de autenticación (`auth_providers`) están modelados por separado, permitiendo múltiples métodos por usuario.

La renovación de sesión se gestiona mediante refresh tokens; se persiste su hash, nunca el valor en claro, permitiendo revocación selectiva.

Ningún token viaja en el cuerpo de una respuesta ni en la cabecera `Authorization`: los endpoints que autentican (`register`, `login`, `google`, `refresh`) los entregan como cookies `httpOnly` — inaccesibles desde JavaScript, lo que cierra la vía más común de robo de tokens vía XSS. Duración, nombres, `Path` y el resto de atributos de cada cookie están documentados en `docs/domains/auth.md` §5, junto con la configuración de CORS que hace falta porque frontend y backend son dominios distintos (ver §5.7).

### 7.2 Control de acceso

Resuelto mediante inyección de dependencias encadenadas:

- **`get_current_user`** — valida el JWT y resuelve el usuario autenticado. Lo lee de la cookie `access_token`, no de una cabecera `Authorization`. Dependencia base de la que dependen las siguientes.
- **`verify_group_membership`** — para endpoints donde el identificador de grupo forma parte de la ruta.
- **`verify_account_access`** — para endpoints que operan sobre un recurso por su propio identificador, resolviendo la pertenencia al grupo antes de autorizar.

### 7.3 Separación entre identidad y autenticación

El dominio `users` gestiona el perfil (`GET /me`, `PATCH /me`) de forma independiente del dominio `auth`, que gestiona exclusivamente el ciclo de autenticación (`POST /auth/login`, `POST /auth/google`, `POST /auth/refresh`, `POST /auth/logout`).

---

## 8. Patrones de acceso a datos

### 8.1 Transacciones financieras

El acceso a transacciones se realiza siempre en el contexto de una cuenta específica (`GET /api/v1/accounts/{account_id}/transactions`), nunca agregando todas las cuentas de un grupo en una sola consulta. El saldo agregado de un grupo se obtiene sumando los saldos ya derivados de sus cuentas — operación válida una vez formalizada la restricción de divisa única por grupo (ver sección 6).

### 8.2 Borrado

El borrado físico es la convención por defecto. El borrado lógico (columna `deleted_at`) es una excepción justificada por dominio, no un patrón transversal — actualmente aplica solo a `transactions`, por razón de integridad del histórico contable. Su comportamiento exacto (incluida la corrección del saldo derivado) se define en el SPEC del dominio `transactions`.

---

## 9. Supuestos no funcionales

- **Volumen de uso**: uso personal o de grupo reducido, no tráfico concurrente de escala SaaS. Justifica la elección de paginación por desplazamiento sobre paginación por cursor, y de una única instancia de base de datos sin réplicas de lectura.
- **Disponibilidad**: sin objetivo de alta disponibilidad definido para el alcance actual.
- **Observabilidad**: fuera de alcance para el MVP; no se define aún estrategia de logging estructurado ni trazabilidad de peticiones.

---

## 10. Estrategia de pruebas

Pruebas automatizadas mediante un framework de testing con soporte de cliente HTTP para pruebas de integración de endpoints. La separación `service`/`repository` permite pruebas unitarias de la lógica de negocio, sustituyendo el repositorio por un doble de prueba, sin infraestructura de persistencia real.

---

## 11. Fuera de alcance (transversal)

- Internacionalización de mensajes de error.
- Rate limiting.
- Observabilidad y logging estructurado.
- Estrategia de despliegue y CI/CD.
- Alta disponibilidad y réplicas de base de datos.

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

Cada uno se redacta inmediatamente antes de comenzar la implementación del dominio correspondiente, no de forma anticipada para todos a la vez.

Además:

- `docs/schema-reference.sql` — diseño de referencia del esquema relacional completo (documentación, no ejecutable).

---

## 13. Mantenimiento del documento

Este documento refleja el estado vigente de las decisiones de arquitectura transversal. Se actualiza cuando una decisión de este nivel cambia; las decisiones de negocio por dominio se mantienen en sus propios documentos.
