# ADR-0005 — Presupuestos como plantilla vigente, no como fila por mes

- **Estado**: aceptada
- **Fecha**: 2026-08-28

## Contexto

Se quiere presupuestar mensualmente por categoría: "400 € al mes en Comida". La pregunta de diseño
es cómo se representa el tiempo, y hay dos familias de respuesta que llevan a esquemas y a
experiencias de uso muy distintas.

Un presupuesto no se cambia casi nunca: se fija una vez y se revisa cada varios meses. Pero cuando
se cambia, hay que poder seguir viendo qué se presupuestó en los meses anteriores, o los informes
históricos mentirían.

## Decisión

Una fila por **periodo de vigencia**, no por mes:

```sql
CREATE TABLE budgets (
    id          UUID   PRIMARY KEY DEFAULT gen_random_uuid(),
    category_id UUID   NOT NULL REFERENCES categories (id) ON DELETE CASCADE,
    amount      BIGINT NOT NULL CHECK (amount > 0),
    valid_from  DATE   NOT NULL,
    valid_to    DATE,            -- NULL = vigente
    ...
    CONSTRAINT chk_budget_period CHECK (valid_to IS NULL OR valid_to > valid_from),
    CONSTRAINT excl_budget_overlap EXCLUDE USING gist (
        category_id WITH =,
        daterange(valid_from, valid_to, '[)') WITH &&
    )
);
```

El intervalo es **semiabierto `[valid_from, valid_to)`**: el día que cierra una fila es el mismo
que abre la siguiente, sin solape ni hueco de un día. Cambiar el importe cierra la fila vigente y
abre otra; el histórico son los rangos.

Consecuencia sobre el contrato HTTP: **no hay `PATCH`, hay `PUT /budgets/{category_id}`**. El
recurso que el usuario manipula es "el presupuesto de la categoría X", no "la fila con id Y". Con
`PATCH /budgets/{budget_id}` habría que explicar por qué modificar `amount` no modifica esa fila
sino que crea otra: un contrato que miente. Como bonus, la clave del path siendo la categoría
permite reutilizar `RequireCategoryOwnerOrAdmin` sin escribir autorización nueva.

**El presupuesto de un mes es el vigente el día 1 de ese mes.** Una fila con `[2026-03-15, NULL)`
no aplica a marzo.

## Consecuencias

- Cero mantenimiento mensual: nadie tiene que crear ni copiar filas al empezar el mes. Un
  presupuesto fijado una vez sigue aplicando indefinidamente.
- El histórico sale gratis y sin filas redundantes: un presupuesto estable durante dos años es una
  fila, no veinticuatro.
- Las consultas son más difíciles de leer que un `WHERE period_month = ...`: hay que comparar
  contra el rango (`valid_from <= ref AND (valid_to IS NULL OR valid_to > ref)`). Es la contrapartida
  principal, y se mitiga concentrando esa condición en el repositorio.
- Cambiar un importe puede implicar **dos escrituras** (cerrar la vigente e insertar la nueva).
  Salen atómicas sin esfuerzo: `get_db()` hace un único `commit` al final de la petición y el
  repositorio solo hace `flush()`.
- **Retrodatar queda fuera de alcance en v1**: un `valid_from` anterior al de la fila vigente
  devuelve `409` en vez de intentar recomponer el histórico.
- El `EXCLUDE` exige la extensión `btree_gist`, que sería **la primera extensión del proyecto**
  (`gen_random_uuid()` es nativo desde PostgreSQL 13). `CREATE EXTENSION` necesita rol privilegiado
  y producción usa el Postgres compartido del VPS: hay que verificarlo antes de escribir la
  migración.
- Un solape lanza `SQLSTATE 23P01`, que hoy nadie traduce y saldría como `500`. Se cubre en dos
  capas: el service cierra la fila vigente antes de insertar (así el constraint solo dispara bajo
  carrera genuina), y un manejador de `IntegrityError` en `app/shared/error_handlers.py` lo traduce
  a `409`.

## Alternativas descartadas

**Una fila por mes** (`period_month DATE`, siempre día 1). Es la más obvia y la más fácil de
consultar. Se descarta porque obliga a materializar filas cada mes —o a inventar un proceso que las
copie— y a decidir qué pasa con los meses futuros que nadie ha creado todavía. Genera doce filas al
año por categoría para representar un número que casi nunca cambia.

**Plantilla recurrente más excepciones por mes** (dos tablas: la plantilla y los *overrides*). Es
la más flexible: permitiría "en agosto subo ocio". Se descarta por complejidad desproporcionada
para v1: dos tablas, un `LEFT JOIN` y un `COALESCE` de precedencia en cada consulta, y un contrato
HTTP que tiene que explicar qué estás editando en cada caso. La plantilla vigente ya permite el
mismo efecto de forma menos cómoda (cerrar y reabrir), y siempre puede evolucionar hacia esto.

**Impedir solapes solo con un índice único parcial** sobre `(category_id) WHERE valid_to IS NULL`
—la técnica que el proyecto ya usa en `uq_auth_providers_local_per_user`—. Garantiza una sola fila
vigente, y sale gratis. Se descarta como solución única porque no impide dos filas *cerradas* que
cubran ambas el mismo mes, y sobre todo **no cierra la carrera** entre dos peticiones concurrentes
que leen la misma fila vigente y ambas insertan. El `EXCLUDE` cubre las tres cosas y lo subsume: un
rango abierto `[from, ∞)` solapa con cualquier rango posterior. Queda como plan B si `btree_gist`
no fuera concedible en el VPS.
