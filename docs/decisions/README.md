# Registros de decisión (ADR)

`ARCHITECTURE.md` documenta el **estado vigente** de las decisiones transversales: se reescribe
cuando una decisión cambia, así que por diseño no conserva el razonamiento de lo que se descartó
ni de por qué algo dejó de ser cierto.

Esta carpeta guarda justamente eso. Un ADR es una foto fechada de una decisión concreta: qué se
sabía, qué se eligió y qué se renunció a cambio.

## Cuándo escribir uno

Solo cuando la decisión cumple alguna de estas:

- **Invierte o contradice** algo que ya estaba documentado.
- **No es evidente** a partir del código: alguien que lea el resultado se preguntaría "¿y por qué
  no de la otra forma?".
- **Asume un riesgo conocido** a cambio de simplicidad, y conviene que quede escrito para poder
  revisarlo cuando el riesgo se materialice.

Lo que no necesita ADR: las convenciones ya recogidas en `ARCHITECTURE.md` o en un SPEC de
dominio, y las decisiones que el propio código explica.

## Cómo se escriben

Un fichero por decisión, `NNNN-titulo-en-kebab-case.md`, numeración correlativa que nunca se
reutiliza. Un ADR **no se edita** cuando la realidad cambia: se escribe uno nuevo que lo sustituya,
y el antiguo pasa a estado `sustituida por ADR-XXXX`. El histórico es el producto.

Estructura: Estado · Contexto · Decisión · Consecuencias · Alternativas descartadas.

## Índice

| ADR | Título | Estado |
|---|---|---|
| [0001](0001-agregados-por-grupo.md) | Los agregados por grupo son una excepción explícita al acceso por cuenta | Aceptada |
| [0002](0002-router-plano-de-consulta.md) | Router plano de consulta junto al CRUD anidado | Aceptada |
| [0003](0003-ancla-de-cobro-derivada.md) | El ancla de cobro se deriva, sin columna nueva | Aceptada |
| [0004](0004-cuentas-gastables-por-tipo.md) | Las cuentas gastables se derivan de `accounts.type` | Aceptada |
| [0005](0005-presupuestos-plantilla-vigente.md) | Presupuestos como plantilla vigente, no como fila por mes | Aceptada |
| [0006](0006-revocar-invitaciones-borrado-fisico.md) | Revocar una invitación la borra, no la marca | Aceptada |
