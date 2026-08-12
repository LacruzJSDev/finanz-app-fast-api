# SPEC de dominio — users

## 1. Problema

La identidad de un usuario (quién es) debe gestionarse de forma independiente de cómo se autentica, para que otros dominios (`accounts`, `transactions`, `account_groups`) puedan referenciar usuarios sin acoplarse a la lógica de autenticación.

## 2. Relación con otros dominios

`auth` depende de `users` (no al revés): crea y consulta filas de `User`, pero la entidad y su gestión de perfil pertenecen a este dominio. `accounts`, `categories`, `payment_plans` y `transactions` referencian `User` en sus columnas `created_by`/`updated_by`, sin lógica adicional sobre él.

## 3. Casos de uso

- Un usuario autenticado consulta su propio perfil.
- Un usuario autenticado actualiza su nombre.
- Un usuario autenticado actualiza su email.

## 4. Endpoints

### `GET /api/v1/me`

Requiere autenticación (`get_current_user`).

- **Salida**: `id`, `email`, `name`, `created_at`.

### `PATCH /api/v1/me`

Requiere autenticación. Actualización parcial (ver convención de `ARCHITECTURE.md` sección 5.5).

- **Entrada**: `name` (opcional), `email` (opcional).
- **Efecto**: actualiza solo los campos presentes en la petición.
- **Errores**: `409` si el nuevo email ya pertenece a otro usuario.

## 5. Reglas de negocio

- El cambio de contraseña no se gestiona aquí — vive en `auth` (`PATCH /api/v1/auth/change_password`), aunque conceptualmente pudiera parecer parte del "perfil". La razón: toca `auth_providers`, no `users`.
- Un cambio de email no invalida las sesiones activas del usuario en v1 (ver sección 6).

## 6. Fuera de alcance (v1)

- Baja de cuenta (`DELETE /me`): requiere decidir primero, en el dominio `account_groups`, qué ocurre cuando el usuario a eliminar es el único `owner` de un grupo con otros miembros. No se implementa hasta cerrar esa dependencia.
- Verificación de email (confirmación por enlace al registrarse o al cambiar de email).
- Invalidación de sesiones activas al cambiar el email o la contraseña.
- Avatar o campos de perfil adicionales más allá de `name`/`email`.

## 7. Criterios de aceptación

- `PATCH /me` enviando solo `{"name": "..."}` no modifica el `email` existente.
- `PATCH /me` con un email ya usado por otro usuario devuelve `409` y no modifica el perfil.
- `GET /me` sin token de autenticación válido devuelve `401`.
