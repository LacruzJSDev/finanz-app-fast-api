# ADR-0004 — Las cuentas gastables se derivan de `accounts.type`

- **Estado**: aceptada
- **Fecha**: 2026-08-28
- **Relacionada**: [ADR-0003](0003-ancla-de-cobro-derivada.md)

## Contexto

El dashboard muestra dos cifras de dinero que **no coinciden**: el patrimonio (todo lo que hay) y
el disponible (lo que financia el gasto del día a día). En la pantalla de referencia son 7267 € de
patrimonio frente a 115 € disponibles.

La diferencia es conceptual, no un error: el dinero de una cuenta de ahorro o de una cuenta de
inversión suma a lo que tienes, pero no es de donde sale la compra del súper. El gasto diario
seguro se calcula sobre el disponible; hacerlo sobre el patrimonio daría una cifra absurda.

Hoy nada en el esquema distingue unas cuentas de otras a este efecto, más allá de
`accounts.type`, que ya existe con los valores `cash`, `bank`, `credit_card`, `savings`,
`investment` y `other`.

## Decisión

Se deriva del tipo, sin columna nueva. En `app/accounts/models.py`, junto al enum:

```python
SPENDABLE_ACCOUNT_TYPES = (
    AccountTypeEnum.CASH,
    AccountTypeEnum.BANK,
    AccountTypeEnum.CREDIT_CARD,
)
```

`savings`, `investment` y `other` quedan fuera: suman a patrimonio, no a disponible.

`credit_card` **entra a propósito**, aunque a primera vista chirríe. El `balance` de una tarjeta de
crédito en este modelo es deuda, es decir, negativo: sumarlo *reduce* el disponible, que es
exactamente el comportamiento correcto. Si debes 200 € en la tarjeta, ese dinero ya no es tuyo
para gastar.

La regla vive en **una sola constante**, no repartida por las consultas, para que cambiarla sea
una línea.

## Consecuencias

- Cero migraciones, y la clasificación ya está hecha: el usuario elige el `type` al crear cada
  cuenta, así que no hay que reclasificar nada a mano.
- **La regla es global, no por cuenta.** Una cuenta `bank` que en realidad sea el colchón de
  emergencia contará como gastable e inflará el gasto diario seguro. Una `savings` de la que
  realmente se gasta quedará fuera. No hay forma de corregirlo caso por caso.
- El gasto de hoy se mide **contra el mismo conjunto de cuentas** del que sale la asignación
  diaria. Si no, se compararían cifras de universos distintos: gasto de todas las cuentas contra un
  presupuesto calculado solo sobre las gastables.
- Cuando la regla global se quede corta, la salida es una columna `accounts.is_spendable`
  booleana, editable por `PATCH`, con el valor inicial derivado del `type` en el backfill de la
  migración — así nadie tendría que reclasificar sus cuentas al actualizar. Sería un ADR nuevo que
  sustituya a este.

## Alternativas descartadas

**Columna `accounts.is_spendable` desde ya.** Es más correcta: explícita, editable y sin adivinar.
Se descarta para esta iteración porque exige migración con backfill, un campo más en `AccountRead`
y en `UpdateAccountRequest`, y una decisión más que tomar al crear cada cuenta — todo para afinar
una clasificación que el `type` ya acierta en la mayoría de los casos. Queda documentada como la
salida natural.

**Usar `balance > 0` o algún umbral** para decidir qué cuenta es gastable. Se descarta por
inestable: la clasificación cambiaría sola de un día para otro según el saldo, y el dashboard daría
cifras distintas sin que el usuario haya tocado nada.
