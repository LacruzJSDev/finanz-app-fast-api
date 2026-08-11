import bcrypt

# bcrypt trunca (o revienta, según la versión) al superar 72 BYTES de entrada,
# no 72 caracteres: con UTF-8 multibyte el límite real llega antes de lo que
# parece. Se valida aquí para dar un error claro en el momento del hash, en
# vez de un ValueError críptico que además dependería de la codificación.
MAX_PASSWORD_BYTES = 72


class PasswordTooLongError(ValueError):
    """La contraseña supera los 72 bytes que admite bcrypt."""


def hash_password(password: str) -> str:
    """Hashea una contraseña usando bcrypt."""
    password_bytes = password.encode("utf-8")
    if len(password_bytes) > MAX_PASSWORD_BYTES:
        raise PasswordTooLongError(
            f"La contraseña supera los {MAX_PASSWORD_BYTES} bytes permitidos"
        )
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password_bytes, salt)
    return hashed.decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    """Verifica que `password` coincide con el hash `hashed` usando bcrypt."""
    password_bytes = password.encode("utf-8")
    if len(password_bytes) > MAX_PASSWORD_BYTES:
        return False
    hashed_bytes = hashed.encode("utf-8")
    return bcrypt.checkpw(password_bytes, hashed_bytes)
