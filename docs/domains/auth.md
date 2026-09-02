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

**Estado**: implementado en la rama `googleOAuth`, no en `dev`. Se deja fuera de `dev` a propósito hasta que el frontend integre el login con Google — sin esa integración no hay forma de probarlo con un token real, y no tiene sentido cargar `dev` con código que todavía no se puede ejercitar de verdad. Al fusionar, revisar que `GOOGLE_CLIENT_ID` esté documentado en `.env.example` y que las dependencias nuevas (`google-auth`, `requests`) sigan al día en `requirements.txt`.

**Nota de implementación**: el paso 1 (verificar el token contra los servidores de Google) es la única dependencia externa real de todo el dominio `auth` — a diferencia de la base de datos, no hay forma razonable de probarlo en un test sin llamar de verdad a Google. Este es el caso concreto en el que sí compensa declarar un puerto formal (`typing.Protocol`) para ese verificador, en vez del acoplamiento directo que se usa para el resto de dependencias del dominio (ver `ARCHITECTURE.md` §2.2). Con el puerto declarado, un test puede inyectar un verificador falso sin tocar la red, y pyright avisa si a ese falso le falta algo que el puerto exige — sin el `Protocol`, ese mismo fallo no se ve hasta que revienta en tiempo de ejecución.

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
- **Errores**: `401` tanto si `current_password` no coincide como si el usuario no tiene ningún método `local` configurado (por ejemplo, se registró solo con Google) — mismo código y mismo mensaje genérico en los dos casos, por la misma razón que en `login`: no confirmar desde la respuesta cómo se registró la cuenta. Para una cuenta sin método `local` este endpoint no aplica; haría falta un flujo de "añadir contraseña", fuera de alcance de v1 (ver sección 7).

## 5. Entrega de tokens: cookies httpOnly

Ningún endpoint devuelve `access_token` ni `refresh_token` como campo del cuerpo JSON. Los dos viajan como cookies `httpOnly`, puestas por el servidor con `Set-Cookie` en la respuesta de `register`, `login`, `google` y `refresh`, y borradas en `logout`.

La razón de no ponerlos en el cuerpo: un token en el JSON de la respuesta solo puede guardarlo el cliente en algún sitio accesible por JavaScript (`localStorage`, una variable en memoria...), y cualquier XSS que consiga ejecutar código en la página puede leerlo de ahí y robarlo. Una cookie `httpOnly` no la puede leer JavaScript bajo ningún concepto — el navegador la adjunta solo a las peticiones, sin que el código de la aplicación llegue a tocar el valor.

Frontend y backend viven en orígenes distintos (no es un caso de mismo origen con rutas `/api`), pero en producción comparten site: `finanzapp.entramaes.com` y `api.finanzapp.entramaes.com` usan HTTPS bajo el mismo dominio registrable. Por eso CORS es necesario, pero no hace falta relajar `SameSite` a `None`.

| Cookie | Path | Contiene | Motivo del `Path` |
|---|---|---|---|
| `access_token` | `/` | JWT de acceso | Hace falta en cualquier endpoint protegido de toda la API. |
| `refresh_token` | `/api/v1/auth` | JWT de refresco | Solo lo necesitan `refresh` y `logout`; restringir el `Path` evita que viaje en cada petición a la API sin necesidad. |

Atributos comunes a las dos:

- **`HttpOnly`** — siempre. Inaccesible desde JavaScript.
- **`Secure`** — solo en producción: una cookie de sesión no puede viajar por HTTP.
- **`SameSite`** — `Lax` en todos los entornos. Entre los dos subdominios HTTPS de producción, igual que entre puertos de `localhost` en desarrollo, sigue siendo una petición same-site y `Lax` permite `fetch`/XHR con credenciales.
- **Expiración** — igual que la del JWT que contienen: `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` / `JWT_REFRESH_TOKEN_EXPIRE_DAYS` (ver sección 6).

El CORS del backend exige el origen exacto del frontend en `CORS_ALLOWED_ORIGINS` (nunca `*`) y `allow_credentials=True`; el cliente manda las peticiones con `credentials: "include"`. Además, una mutación que ya incluya `access_token` o `refresh_token` debe llevar una cabecera `Origin` incluida en esa lista; si no, responde `403`. Esto evita CSRF sin exponer un token a JavaScript. Ver `ARCHITECTURE.md` §5.7.

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
- Un `change_password` con la contraseña actual incorrecta y un `change_password` sobre una cuenta sin método `local` (por ejemplo, registrada solo con Google) devuelven la misma respuesta `401`, indistinguible entre sí.
- Un `logout`, `refresh` o `change_password` que reciba una cookie de autenticación sin un `Origin` permitido devuelve `403` con el contrato de error común.
