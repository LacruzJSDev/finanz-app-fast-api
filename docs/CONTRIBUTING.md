# Convenciones de trabajo

## 1. Mensajes de commit

Se sigue [Conventional Commits](https://www.conventionalcommits.org/), **en inglés**.

El inglés no es un capricho: el 99% de lo que aparece en un log de Git es en
inglés (nombres de ficheros, de funciones, de ramas, mensajes de las
herramientas), y mezclar idiomas dentro de la misma línea se lee mal. Los
comentarios del código y la documentación de `docs/` sí van en español, que es
donde se explica el *porqué* con matices.

### 1.1 Formato

```
<tipo>(<ámbito>): <asunto>

<cuerpo opcional>

<pie opcional>
```

Solo la primera línea es obligatoria.

### 1.2 Tipos

| Tipo | Cuándo |
|---|---|
| `feat` | Funcionalidad nueva visible para quien usa la API |
| `fix` | Corrección de un comportamiento incorrecto |
| `docs` | Solo documentación |
| `refactor` | Reestructuración sin cambiar el comportamiento |
| `test` | Añadir o corregir pruebas |
| `perf` | Cambio orientado al rendimiento |
| `build` | Sistema de construcción o dependencias (Docker, requirements) |
| `ci` | Configuración de integración continua |
| `chore` | Mantenimiento que no encaja arriba (.gitignore, config de editor) |

La pregunta que resuelve las dudas: **¿qué le pasa a quien consume la API?**
Si gana algo, `feat`. Si algo que estaba roto deja de estarlo, `fix`. Si no
nota nada, es una de las demás.

### 1.3 Ámbito

Entre paréntesis, opcional pero recomendable. En este proyecto el ámbito es
normalmente el dominio o la pieza transversal tocada:

`users`, `auth`, `accounts`, `account-groups`, `categories`, `transactions`,
`payment-plans`, `budgets`, `db`, `api`, `config`, `docker`, `deps`

Si un commit toca tantos ámbitos que no sabes cuál poner, probablemente
deberían ser varios commits.

### 1.4 El asunto

- En **imperativo**: `add`, `fix`, `remove` — no `added`, `adds`, `adding`.
  La regla mnemotécnica: el mensaje completa la frase *"This commit will…"*.
- En **minúscula** y **sin punto final**.
- **50 caracteres o menos.** Es el ancho que muestra `git log --oneline` sin
  cortar, y en GitHub a partir de 72 se trunca con puntos suspensivos.
- Describe **el cambio**, no el fichero. `add user model` , no
  `modify models.py`.

### 1.5 El cuerpo

Se separa del asunto con una línea en blanco y se ajusta a 72 columnas.

Solo hace falta cuando el *porqué* no es evidente. El *qué* ya está en el
diff; lo que el diff no cuenta es qué alternativa descartaste y por qué. Un
commit que arregla algo raro sin explicar el motivo es un commit que dentro de
seis meses nadie se atreve a tocar.

### 1.6 Cambios que rompen compatibilidad

Un `!` antes de los dos puntos, y un pie explicándolo:

```
feat(api)!: return paginated envelope from list endpoints

BREAKING CHANGE: los endpoints de colección devuelven
{items, total, limit, offset} en vez de un array plano.
```

### 1.7 Ejemplos

Reescritos a partir de commits reales de este repositorio:

| Antes | Después |
|---|---|
| `Añadir README con pasos de setup del proyecto` | `docs: add project setup guide` |
| `Configurar debugger de VS Code para FastAPI` | `chore: add vscode debug configuration` |
| `Ajustar formato de comentario en docker-compose.yml` | `style(docker): fix comment formatting` |
| `Añadir soporte para múltiples métodos de autenticación y crear tabla de proveedores de autenticación al esquema documentado en sql` | `docs(auth): add auth_providers table to schema reference` |

El último es además un caso de commit que hacía dos cosas a la vez: soporte
para varios métodos de autenticación *y* la tabla nueva. Son dos commits.

Uno con cuerpo, cuando el porqué importa:

```
fix(db): keep updated_at current with a trigger

server_default=NOW() solo se aplica en el INSERT, así que la columna
se quedaba congelada en la fecha de creación.

Se resuelve con un trigger en Postgres y no con onupdate de SQLAlchemy
para que también cubra los UPDATE que no pasan por el ORM: migraciones,
scripts de mantenimiento o un psql a mano.
```

### 1.8 Qué NO poner en un mensaje

- Números de tarea sin más (`fix TICKET-42`): el mensaje tiene que entenderse
  sin salir del repositorio. La referencia va en el pie (`Refs: TICKET-42`).
- `wip`, `cambios varios`, `arreglos`, `.` — si de verdad es trabajo a medias,
  úsalo en local y aplástalo con `git rebase -i` antes de subirlo.
- El nombre del fichero como único contenido.

---

## 2. Commits atómicos

Un commit = un cambio lógico completo. Dos criterios prácticos:

1. **Cada commit deja el proyecto funcionando.** Si hay que aplicar dos
   commits seguidos para que arranque, eran uno solo.
2. **Se puede revertir solo.** Si al hacer `git revert` de un commit te
   llevas por delante algo sin relación, estaban mezclados.

Un modelo nuevo y su migración de Alembic van **en el mismo commit**: por
separado, el commit del modelo deja el esquema desincronizado con el código.

Si al terminar de trabajar tienes cambios mezclados, `git add -p` permite
elegir trozo a trozo qué entra en cada commit.

---

## 3. Ramas

- `main` — estado estable.
- `dev` — integración del trabajo en curso.
- `<tipo>/<descripción-corta>` — una rama por cambio, partiendo de `dev`:
  `feat/google-oauth`, `fix/balance-on-transfer-delete`.

Mismos tipos y mismo inglés que en los commits.

---

## 4. Antes de hacer commit

```bash
ruff check . --fix
ruff format .
pytest
```

Cuando falta algo en una migración, es más limpio corregir la migración y
regenerarla que añadir una segunda migración parche encima — **siempre que no
se haya subido todavía**. Una vez que una migración está en `origin`, ya hay
bases de datos que la han aplicado: a partir de ahí, solo se corrige con una
migración nueva.

La misma regla vale para el historial: reescribir commits ya publicados
(`rebase`, `commit --amend`) rompe el repositorio a quien ya se lo haya
bajado. Los commits antiguos de este repositorio se quedan como están; la
convención aplica de aquí en adelante.

### Plantilla de mensaje (opcional)

Para que `git commit` abra el editor con la chuleta delante:

```bash
git config commit.template .gitmessage
```
