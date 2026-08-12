# SPEC de dominio — auth

## 1. Problema

Los usuarios necesitan demostrar su identidad para acceder a sus datos, mediante credenciales propias (email y contraseña) o mediante un proveedor externo (Google), sin que la aplicación gestione dos sistemas de identidad separados para cada caso.

## 2. Relación con otros dominios

Este dominio depende de `users` (crea y consulta filas de `User`, nunca al revés). No contiene la entidad `User` ni expone su gestión de perfil — eso pertenece a `docs/domains/users.md`.

## 3. Casos de uso

- Un usuario nuevo se registra con email y contraseña.
- Un usuario registrado inicia sesión con email y contraseña.
- Un usuario inicia sesión con Google, sin haberse registrado antes con ese email — se crea la identidad y el método de autenticación en la misma operación.
- Un usuario ya registrado por email/contraseña inicia sesión con Google usando el mismo email — el nuevo método se vincula a su identidad existente, no se crea un usuario duplicado.
- Un cliente renueva su token de acceso usando un refresh token válido.
- Un usuario cierra sesión, invalidando el refresh token usado.
- Un usuario cambia su contraseña estando autenticado.

## 4. Endpoints

### `POST /api/v1/auth/register`

Registro con credenciales locales.

- **Entrada**: `email`, `password`, `name`.
- **Efecto**: crea `User` y una fila `auth_providers` (`provider = 'local'`, `password_hash` con hash de la contraseña).
- **Salida**: el `User` creado, en el cuerpo. `access_token` y `refresh_token` se entregan como cookies httpOnly, no como campos del JSON (ver sección 5) — el registro autentica inmediatamente, sin exigir un login posterior.
- **Errores**: `409` si el email ya existe.

### `POST /api/v1/auth/login`

Inicio de sesión con credenciales locales.

- **Entrada**: `email`, `password`.
- **Efecto**: valida contra la fila `auth_providers` de tipo `local` del usuario con ese email. Crea una fila en `sessions` con el hash del refresh token emitido.
- **Salida**: el `User` autenticado, en el cuerpo. `access_token` y `refresh_token` como cookies httpOnly (ver sección 5).
- **Errores**: `401` si el email no existe o la contraseña no coincide (mismo código y mismo mensaje genérico en ambos casos, para no confirmar qué emails están registrados).

### `POST /api/v1/auth/google`

Inicio de sesión o registro mediante Google.

- **Entrada**: token de identidad emitido por Google.
- **Efecto**:
  1. Verifica el token contra los servidores de Google.
  2. Si ya existe una fila `auth_providers` (`provider = 'google'`, `provider_user_id` = identificador de Google) → usa el `User` asociado.
  3. Si no existe esa fila, pero el email ya pertenece a un `User` existente (por ejemplo, registrado antes con `local`) → vincula la nueva fila `auth_providers` a ese usuario.
  4. Si el email no existe en absoluto → crea `User` y la fila `auth_providers` en la misma operación.
  5. Crea sesión, igual que en `login`.
- **Salida**: el `User`, en el cuerpo. `access_token` y `refresh_token` como cookies httpOnly (ver sección 5).
- **Errores**: `401` si el token de Google no es válido o no se puede verificar.

### `POST /api/v1/auth/refresh`

Renovación del token de acceso.

- **Entrada**: ninguna en el cuerpo — el `refresh_token` se lee de su cookie (ver sección 5), no se manda explícitamente.
- **Efecto**: valida el hash contra `sessions.refresh_token_hash`, comprueba que la sesión no esté revocada ni expirada. Emite un nuevo `access_token`. El `refresh_token` se rota (se invalida el usado y se emite uno nuevo), para reducir la ventana de uso de un token filtrado.
- **Salida**: el `User`, en el cuerpo — igual que `login`/`register`: el cliente lo guarda en memoria y lo necesita ahí sin tener que pedirlo aparte. `access_token` y `refresh_token` como cookies httpOnly (ver sección 5).
- **Errores**: `401` si el refresh token no es válido, está revocado o expirado.

### `POST /api/v1/auth/logout`

Cierre de sesión.

- **Entrada**: ninguna en el cuerpo — el `refresh_token` de la sesión a cerrar se lee de su cookie.
- **Efecto**: marca la fila correspondiente de `sessions` como `revoked = true`. No afecta a otras sesiones activas del mismo usuario en otros dispositivos.
- **Salida**: `204 No Content`. Borra las dos cookies (ver sección 5).

### `PATCH /api/v1/auth/change_password`

Cambio de contraseña, requiere autenticación.

- **Entrada**: `current_password`, `new_password`.
- **Efecto**: valida la contraseña actual contra la fila `local` existente, actualiza `password_hash`.
- **Errores**: `401` si `current_password` no coincide. `404`/`409` si el usuario no tiene un método `local` configurado (por ejemplo, se registró solo con Google) — en ese caso este endpoint no aplica; se necesitaría un flujo de "añadir contraseña", fuera de alcance de v1 (ver sección 7).

## 5. Entrega de tokens: cookies httpOnly

Ningún endpoint devuelve `access_token` ni `refresh_token` como campo del cuerpo JSON. Los dos viajan como cookies `httpOnly`, puestas por el servidor con `Set-Cookie` en la respuesta de `register`, `login`, `google` y `refresh`, y borradas en `logout`.

La razón de no ponerlos en el cuerpo: un token en el JSON de la respuesta solo puede guardarlo el cliente en algún sitio accesible por JavaScript (`localStorage`, una variable en memoria...), y cualquier XSS que consiga ejecutar código en la página puede leerlo de ahí y robarlo. Una cookie `httpOnly` no la puede leer JavaScript bajo ningún concepto — el navegador la adjunta solo a las peticiones, sin que el código de la aplicación llegue a tocar el valor.

Frontend y backend viven en dominios distintos (no es un caso de mismo dominio con rutas `/api`), así que esto es una cookie **cross-site** de verdad, con las implicaciones que conlleva:

| Cookie | Path | Contiene | Motivo del `Path` |
|---|---|---|---|
| `access_token` | `/` | JWT de acceso | Hace falta en cualquier endpoint protegido de toda la API. |
| `refresh_token` | `/api/v1/auth` | JWT de refresco | Solo lo necesitan `refresh` y `logout`; restringir el `Path` evita que viaje en cada petición a la API sin necesidad. |

Atributos comunes a las dos:

- **`HttpOnly`** — siempre. Inaccesible desde JavaScript.
- **`Secure`** — solo en producción. Obligatorio en cuanto `SameSite=None`; en desarrollo, con todo bajo `localhost`, no hace falta.
- **`SameSite`** — `None` en producción (dominios registrables distintos, cookie cross-site real); `Lax` en desarrollo (frontend y backend comparten `localhost`, aunque en puertos distintos, y `Lax` ya basta para peticiones `fetch`/XHR entre ellos).
- **Expiración** — igual que la del JWT que contienen: `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` / `JWT_REFRESH_TOKEN_EXPIRE_DAYS` (ver sección 6).

Con credenciales viajando en cookies cross-site, el CORS del backend exige el origen exacto del frontend en `CORS_ALLOWED_ORIGINS` (nunca `*`) y `allow_credentials=True`; el cliente, por su parte, tiene que mandar sus peticiones con `credentials: "include"` (o el equivalente de su librería HTTP) para que el navegador adjunte las cookies. Ver `ARCHITECTURE.md` §5.7.

## 6. Reglas de negocio

- Un usuario puede tener como máximo un método `local` (impuesto por índice único parcial en el esquema) y múltiples métodos externos, uno por proveedor distinto.
- La vinculación automática por coincidencia de email (caso de uso 4) se basa en que `users.email` es único: si el email de la cuenta de Google ya existe como `User`, no puede crearse un `User` nuevo con ese email, así que la única operación coherente es vincular.
- El email se normaliza (`strip` + minúsculas) en el propio esquema de entrada, antes de tocar la base de datos — así el mismo email con distinto formato de mayúsculas se reconoce como el mismo usuario tanto al registrarse como al iniciar sesión.
- El payload del JWT de acceso contiene el identificador del usuario y su expiración; no contiene datos sensibles ni el rol/pertenencia a grupos (eso se resuelve en cada petición contra la base de datos, no se cachea en el token).
- Duración por defecto: token de acceso 30 minutos; refresh token 7 días. Configurables vía `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` / `JWT_REFRESH_TOKEN_EXPIRE_DAYS` (ver `ARCHITECTURE.md`).
- El logout es por sesión (dispositivo), no revoca el resto de sesiones activas del usuario.

## 7. Fuera de alcance (v1)

- Recuperación de contraseña olvidada (flujo de email con token de restablecimiento) — cuando se implemente, será `POST /api/v1/auth/recover_password`, distinto de `change_password`: no requiere autenticación ni contraseña actual, solo el token de restablecimiento recibido por email.
- Autenticación de dos factores.
- Flujo explícito de "añadir contraseña" a una cuenta que solo tiene Google vinculado.
- Cierre de sesión en todos los dispositivos a la vez.
- Listado de sesiones activas visibles para el usuario.
- Otros proveedores OAuth distintos de Google.

## 8. Criterios de aceptación

- Un registro con un email ya existente devuelve `409`, sin crear ninguna fila.
- Un login con contraseña incorrecta y un login con email inexistente devuelven la misma respuesta `401`, indistinguible entre sí.
- Ninguna respuesta de `register`, `login`, `google` o `refresh` incluye `access_token` ni `refresh_token` en el cuerpo JSON; ambos llegan exclusivamente como cookies `httpOnly`.
- Tras un `refresh`, el refresh token anterior deja de ser válido para una nueva renovación.
- Un `refresh` con la cookie `refresh_token` de una sesión ya expirada (`expires_at` en el pasado) devuelve `401`, sin emitir tokens nuevos.
- Tras un `logout`, el refresh token usado deja de ser válido para `refresh`, pero el resto de sesiones del usuario en otros dispositivos siguen activas.
- Un login con Google usando un email ya registrado por `local` no crea un segundo `User`; ambos métodos quedan vinculados al mismo `User`.
