import hashlib


def hash_token(token: str) -> str:
    """Hash determinista de un token largo, para guardarlo en la base de datos.

    No usa bcrypt: bcrypt es lento y salado a propósito, pensado para
    contraseñas cortas que un atacante podría intentar adivinar por fuerza
    bruta. Un refresh token ya es un secreto de alta entropía (lo genera el
    propio JWT, nadie lo escribe a mano); aquí el hash solo evita guardar el
    valor en claro, y hace falta que sea determinista para poder buscarlo por
    igualdad en `sessions.refresh_token_hash` sin desencriptar nada.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
