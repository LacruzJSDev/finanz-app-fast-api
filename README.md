# FinanzApp — API

Backend de una aplicación de finanzas personales multiusuario. FastAPI +
PostgreSQL + Alembic, todo sobre Docker.

Las decisiones de arquitectura están en [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md);
el diseño del modelo de datos, en [`docs/schema-reference.sql`](docs/schema-reference.sql);
las convenciones de commits y ramas, en [`docs/CONTRIBUTING.md`](docs/CONTRIBUTING.md).

---

## Puesta en marcha

```bash
cp .env.example .env
```

Edita `.env` y pon al menos `POSTGRES_PASSWORD`, un `DATABASE_URL` coherente
con esa contraseña y un `SECRET_KEY`. Para generar la clave:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

Y arranca:

```bash
docker compose up --build
```

Eso levanta Postgres, espera a que esté sano, aplica las migraciones
pendientes y arranca la API con recarga automática.

- API: http://localhost:8000
- Documentación interactiva: http://localhost:8000/docs
- Health check: http://localhost:8000/health
- Postgres (desde el host): `localhost:5433`

---

## Desarrollo vs producción

El `docker-compose.yml` de este repo es **solo para desarrollo** (código
montado desde el host, `--reload`, Postgres publicado en 5433). El compose de
producción vive en el repo de infra
(`entramaes-infra/apps/finanzapp/compose.yaml`), que conecta la API al
Postgres y al Caddy compartidos del VPS; el workflow de despliegue
(`.github/workflows/deploy.yml`) hace `docker compose pull` sobre ese fichero
al mergear a `main`.

`.env` nunca entra en la imagen (`.dockerignore` lo excluye): las variables se
inyectan en tiempo de ejecución vía `env_file`. En un despliegue real, `.env`
vive en el servidor, no en el repositorio.

---

## Entorno local (fuera de Docker)

Hace falta para generar migraciones y ejecutar los tests. La base de datos
sigue siendo la del contenedor — por eso el `DATABASE_URL` de `.env` apunta a
`localhost:5433`.

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements-dev.txt
```

---

## Migraciones

**Se generan desde el host** (necesitan escribir ficheros nuevos) y **se
aplican solas dentro del contenedor** (el `entrypoint.sh` ejecuta
`alembic upgrade head` en cada arranque).

Después de crear o modificar un modelo, hay que registrarlo en
[`app/db_registry.py`](app/db_registry.py) — si no, Alembic no lo ve y
propondrá borrar sus tablas. Luego:

```bash
alembic revision --autogenerate -m "descripcion del cambio"
```

Revisa siempre el fichero generado antes de aplicarlo: el autogenerate no
detecta renombrados (los interpreta como borrar + crear, con pérdida de datos)
ni nada que no esté expresado en los modelos, como triggers o índices
parciales. Eso se añade a mano con `op.execute()`.

Para aplicarlas basta con reiniciar la API:

```bash
docker compose restart api
```

Otros comandos útiles:

```bash
alembic current
alembic history --verbose
alembic downgrade -1
```

---

## Tests

```bash
pytest
```

---

## Estructura

```
alembic/versions/    Migraciones — la fuente de verdad del esquema
app/config.py        Settings leídas del entorno al arrancar
app/database.py      Engine, SessionLocal, Base y la dependencia get_db
app/db_registry.py   Importa todos los modelos para que Alembic los vea
app/main.py          Instancia de FastAPI
app/<dominio>/       Un paquete por dominio: router, service, repository,
                     models, schemas
docs/                Arquitectura y diseño del modelo de datos
```
