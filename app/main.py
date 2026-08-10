from fastapi import FastAPI

app = FastAPI(title="FinanzApp API", version="0.1.0")


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    """Comprobación de disponibilidad, sin autenticación ni lógica de negocio.

    La usa el healthcheck de Docker para saber si el contenedor está listo
    (ver ARCHITECTURE.md §5.8). No consulta la base de datos a propósito: mide
    si el proceso responde, no si sus dependencias están sanas.
    """
    return {"status": "ok"}
