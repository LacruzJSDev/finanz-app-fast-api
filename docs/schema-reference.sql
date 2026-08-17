-- =============================================================
-- FinanzApp — Esquema de referencia (DOCUMENTACIÓN)
-- =============================================================
--
--   ⚠️  ESTE FICHERO NO SE EJECUTA NUNCA.
--
-- Es el diseño de referencia del modelo de datos completo, escrito
-- antes de empezar a implementar. La fuente de verdad del esquema
-- real son las migraciones de Alembic (alembic/versions/), que se
-- aplican solas al arrancar el contenedor.
--
-- Cada vez que se implementa un dominio, sus tablas se traducen de
-- aquí a una migración de Alembic. Los triggers y funciones se
-- portan con op.execute() dentro de la migración.
--
-- Si al traducir una tabla se descubre que el diseño de aquí estaba
-- mal, se corrige ESTE fichero también: es documentación viva, no un
-- histórico congelado.
--
-- Estado de la traducción a Alembic:
--   [x] users
--   [x] auth_providers
--   [x] sessions
--   [ ] account_groups
--   [ ] account_group_members
--   [ ] invitations
--   [ ] accounts
--   [ ] categories
--   [ ] payment_plans
--   [ ] transactions
--
-- =============================================================
-- Aplicación de finanzas personales multiusuario. El dominio se
-- organiza alrededor de "grupos de cuentas" (account_groups): un
-- grupo puede representar a una persona sola o a varias personas
-- compartiendo finanzas (pareja, piso compartido, etc.), y todo
-- lo demás (cuentas, categorías, transacciones, planes de pago)
-- cuelga de un grupo, nunca directamente de un usuario. Esto es
-- lo que permite que varios usuarios vean y editen las mismas
-- cuentas sin duplicar datos.
--
-- Autenticación: identidad (users) y método de autenticación
-- (auth_providers) están separados a propósito. Un usuario puede
-- registrarse con Google y más tarde añadir contraseña como
-- método alternativo, o viceversa — por eso la contraseña NO
-- vive en users, vive en auth_providers junto al resto de
-- métodos de login.
-- =============================================================

-- =============================================================
-- ENUMS
-- =============================================================

-- Rol de un usuario dentro de un grupo de cuentas.
CREATE TYPE role_enum AS ENUM ('owner', 'admin', 'member');

-- Estado de una invitación a unirse a un grupo.
CREATE TYPE status_enum AS ENUM ('pending', 'accepted', 'expired');

-- Naturaleza de una transacción. 'transfer' es un movimiento entre
-- dos cuentas del propio usuario/grupo, no un ingreso ni un gasto.
CREATE TYPE transaction_type_enum AS ENUM ('income', 'expense', 'transfer');

CREATE TYPE frequency_unit_enum AS ENUM ('day', 'week', 'month', 'year');

CREATE TYPE account_type_enum AS ENUM ('cash', 'bank', 'credit_card', 'savings', 'investment', 'other');

-- Método de autenticación vinculado a un usuario. 'local' significa
-- login con email+contraseña gestionado por nosotros; cualquier
-- otro valor es un proveedor OAuth externo (Google verifica la
-- identidad, nosotros solo confiamos en su token).
CREATE TYPE auth_provider_enum AS ENUM ('local', 'google');


-- =============================================================
-- FUNCIONES COMUNES
-- =============================================================

-- Mantiene updated_at al día en cada UPDATE. server_default = NOW()
-- solo actúa en el INSERT, así que sin este trigger la columna se
-- quedaría congelada en la fecha de creación. La función es genérica:
-- toda tabla con columna updated_at cuelga de ella su propio trigger
-- (ver la línea CREATE TRIGGER al final de cada tabla).
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at := NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;


-- =============================================================
-- USERS
-- Identidad de cada persona que usa la aplicación. Independiente
-- de a cuántos grupos pertenezca y de cómo se autentique — por
-- eso ya NO tiene columna password (ver auth_providers).
-- =============================================================

CREATE TABLE users (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email         VARCHAR(255) NOT NULL UNIQUE,
    name          VARCHAR(100) NOT NULL,
    created_at    TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_users_email ON users (email);

CREATE TRIGGER trg_users_set_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW
    EXECUTE FUNCTION set_updated_at();


-- =============================================================
-- AUTH PROVIDERS
-- Métodos de autenticación vinculados a un usuario. Un usuario
-- puede tener varios (ej. registrarse con Google y más tarde
-- añadir contraseña como método alternativo). password_hash solo
-- se rellena cuando provider = 'local'; provider_user_id (el
-- "sub" que manda el proveedor externo) solo cuando no lo es.
-- El CHECK impone esta exclusividad a nivel de base de datos, no
-- solo en el código de la aplicación.
-- =============================================================

CREATE TABLE auth_providers (
    id                UUID                PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id           UUID                NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    provider          auth_provider_enum  NOT NULL,
    provider_user_id  VARCHAR(255),
    password_hash     VARCHAR(255),
    created_at        TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),

    CONSTRAINT chk_provider_fields CHECK (
        (provider = 'local'  AND password_hash IS NOT NULL AND provider_user_id IS NULL) OR
        (provider <> 'local' AND provider_user_id IS NOT NULL AND password_hash IS NULL)
    ),
    CONSTRAINT uq_provider_identity UNIQUE (provider, provider_user_id)
);

CREATE INDEX idx_auth_providers_user_id ON auth_providers (user_id);

-- uq_provider_identity NO basta para impedir que un mismo usuario
-- tenga dos filas 'local': provider_user_id es siempre NULL en esas
-- filas, y Postgres no considera que dos NULL "choquen" en un UNIQUE.
-- Este índice parcial cierra ese hueco: como mucho una fila 'local'
-- por usuario (no tiene sentido tener dos contraseñas para el mismo
-- usuario).
CREATE UNIQUE INDEX uq_auth_providers_local_per_user
    ON auth_providers (user_id)
    WHERE provider = 'local';


-- =============================================================
-- SESSIONS
-- Sesiones de autenticación activas por usuario. Se revocan
-- explícitamente (revoked = true) en vez de borrarse, para
-- mantener trazabilidad de accesos. refresh_token_hash guarda el
-- hash (ej. SHA-256) del refresh token, nunca el token en texto
-- plano — si alguien accede a la base de datos, no puede robar
-- sesiones activas directamente de una columna legible.
-- =============================================================

CREATE TABLE sessions (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    refresh_token_hash  VARCHAR(255) NOT NULL,
    revoked             BOOLEAN NOT NULL DEFAULT FALSE,
    expires_at          TIMESTAMP WITH TIME ZONE NOT NULL,
    created_at          TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_sessions_user_id ON sessions (user_id);
CREATE UNIQUE INDEX idx_sessions_refresh_token_hash ON sessions (refresh_token_hash);


-- =============================================================
-- ACCOUNT GROUPS
-- Unidad central del modelo: agrupa cuentas, categorías y
-- transacciones bajo un mismo espacio compartido. is_active
-- permite archivar un grupo (por ejemplo, al terminar una
-- convivencia) sin destruir su historial financiero.
-- =============================================================

CREATE TABLE account_groups (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name       VARCHAR(100) NOT NULL,
    color      VARCHAR(7),
    icon       VARCHAR(50),
    is_active  BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE TRIGGER trg_account_groups_set_updated_at
    BEFORE UPDATE ON account_groups
    FOR EACH ROW
    EXECUTE FUNCTION set_updated_at();


-- =============================================================
-- ACCOUNT GROUP MEMBERS
-- Relación muchos-a-muchos entre users y account_groups, con un
-- rol asociado. Quién invitó a quién no se guarda aquí, sino en
-- invitations — esta tabla solo representa la pertenencia vigente.
-- =============================================================

CREATE TABLE account_group_members (
    id         UUID      PRIMARY KEY DEFAULT gen_random_uuid(),
    group_id   UUID      NOT NULL REFERENCES account_groups (id) ON DELETE CASCADE,
    user_id    UUID      NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    role       role_enum NOT NULL DEFAULT 'member',
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_group_member UNIQUE (group_id, user_id)
);

CREATE INDEX idx_group_members_group_id ON account_group_members (group_id);
CREATE INDEX idx_group_members_user_id  ON account_group_members (user_id);

CREATE TRIGGER trg_account_group_members_set_updated_at
    BEFORE UPDATE ON account_group_members
    FOR EACH ROW
    EXECUTE FUNCTION set_updated_at();


-- =============================================================
-- INVITATIONS
-- Ciclo de vida de una invitación a un grupo: quién la envía,
-- con qué rol, y quién y cuándo la acepta (si llega a aceptarse).
-- invited_by/accepted_by usan ON DELETE SET NULL: el historial de
-- invitaciones sobrevive aunque el usuario que invitó o aceptó
-- borre su cuenta más adelante.
-- =============================================================

CREATE TABLE invitations (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    group_id    UUID        NOT NULL REFERENCES account_groups (id) ON DELETE CASCADE,
    invited_by  UUID        REFERENCES users (id) ON DELETE SET NULL,
    role        role_enum   NOT NULL DEFAULT 'member',
    code        VARCHAR(20) NOT NULL UNIQUE,
    status      status_enum NOT NULL DEFAULT 'pending',
    accepted_by UUID        REFERENCES users (id) ON DELETE SET NULL,
    accepted_at TIMESTAMP WITH TIME ZONE,
    expires_at  TIMESTAMP WITH TIME ZONE NOT NULL,
    created_at  TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_invitations_group_id ON invitations (group_id);
CREATE INDEX idx_invitations_code     ON invitations (code);


-- =============================================================
-- ACCOUNTS
-- Cada cuenta financiera (banco, efectivo, tarjeta, inversión...)
-- pertenece a un grupo, nunca a un usuario directamente.
--
-- balance es un valor DERIVADO, no de entrada: se calcula a partir
-- de opening_balance (el saldo con el que arrancó la cuenta) más
-- el efecto acumulado de sus transacciones. Se mantiene siempre
-- mediante triggers (ver más abajo), nunca escrito a mano desde
-- la aplicación — así el saldo no puede desincronizarse por un
-- caso olvidado en el código.
--
-- Los importes se guardan en BIGINT (céntimos, ej. 10.50€ = 1050)
-- en vez de DECIMAL/FLOAT para evitar errores de redondeo en
-- aritmética financiera.
--
-- created_by/updated_by usan ON DELETE SET NULL: borrar un usuario
-- no debe bloquear ni arrastrar en cascada las cuentas del grupo.
-- =============================================================

CREATE TABLE accounts (
    id              UUID              PRIMARY KEY DEFAULT gen_random_uuid(),
    group_id        UUID              NOT NULL REFERENCES account_groups (id) ON DELETE CASCADE,
    name            VARCHAR(100)      NOT NULL,
    type            account_type_enum NOT NULL DEFAULT 'bank',
    opening_balance BIGINT            NOT NULL DEFAULT 0,
    balance         BIGINT            NOT NULL DEFAULT 0,
    currency        VARCHAR(3)        NOT NULL DEFAULT 'EUR',
    color           VARCHAR(7),
    icon            VARCHAR(50),
    is_active       BOOLEAN           NOT NULL DEFAULT TRUE,
    created_by      UUID              REFERENCES users (id) ON DELETE SET NULL,
    updated_by      UUID              REFERENCES users (id) ON DELETE SET NULL,
    created_at      TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_accounts_group_id ON accounts (group_id);

CREATE TRIGGER trg_accounts_set_updated_at
    BEFORE UPDATE ON accounts
    FOR EACH ROW
    EXECUTE FUNCTION set_updated_at();

-- Invariante: balance siempre nace igual a opening_balance. A
-- partir de ahí, solo lo tocan los triggers de transactions.
CREATE OR REPLACE FUNCTION init_account_balance()
RETURNS TRIGGER AS $$
BEGIN
    NEW.balance := NEW.opening_balance;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_init_account_balance
    BEFORE INSERT ON accounts
    FOR EACH ROW
    EXECUTE FUNCTION init_account_balance();


-- =============================================================
-- CATEGORIES
-- Clasificación de transacciones (comida, transporte, nómina...),
-- agnóstica al tipo de movimiento — el tipo vive en
-- transactions.type, no aquí, porque una misma categoría puede
-- en principio aplicarse tanto a ingresos como a gastos.
--
-- Jerarquía deliberadamente limitada a dos niveles: una categoría
-- raíz (parent_id IS NULL) o una subcategoría de una raíz. No se
-- permiten subcategorías de subcategorías, para mantener la
-- interfaz de selección simple. Esta invariante no se puede
-- expresar con una FK normal, así que se impone con un trigger.
-- =============================================================

CREATE TABLE categories (
    id         UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    group_id   UUID         NOT NULL REFERENCES account_groups (id) ON DELETE CASCADE,
    parent_id  UUID         REFERENCES categories (id) ON DELETE SET NULL,
    name       VARCHAR(100) NOT NULL,
    color      VARCHAR(7),
    icon       VARCHAR(50),
    is_active  BOOLEAN      NOT NULL DEFAULT TRUE,
    created_by UUID         REFERENCES users (id) ON DELETE SET NULL,
    updated_by UUID         REFERENCES users (id) ON DELETE SET NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_categories_group_id  ON categories (group_id);
CREATE INDEX idx_categories_parent_id ON categories (parent_id);

CREATE TRIGGER trg_categories_set_updated_at
    BEFORE UPDATE ON categories
    FOR EACH ROW
    EXECUTE FUNCTION set_updated_at();

-- Invariante: máximo dos niveles de profundidad, y una categoría
-- no puede ser su propia categoría padre.
CREATE OR REPLACE FUNCTION check_category_depth()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.parent_id IS NOT NULL THEN
        IF NEW.parent_id = NEW.id THEN
            RAISE EXCEPTION 'Una categoría no puede ser su propia categoría padre.';
        END IF;
        IF (SELECT parent_id FROM categories WHERE id = NEW.parent_id) IS NOT NULL THEN
            RAISE EXCEPTION 'No se permiten subcategorías de subcategorías. La categoría padre debe ser una categoría raíz.';
        END IF;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_check_category_depth
    BEFORE INSERT OR UPDATE ON categories
    FOR EACH ROW
    EXECUTE FUNCTION check_category_depth();


-- =============================================================
-- PAYMENT PLANS
-- Movimientos futuros/recurrentes ya conocidos (una nómina, un
-- alquiler, una suscripción) que aún no han ocurrido como
-- transacción real. to_account_id permite modelar un plan que en
-- su día se ejecutará como transferencia entre dos cuentas.
--
-- type reutiliza transaction_type_enum: un plan es la plantilla de
-- la transacción que generará, así que necesita saber de antemano
-- si esa transacción será income, expense o transfer — sin esta
-- columna no habría forma de saberlo al materializarlo. amount es
-- siempre una magnitud positiva (chk_amount > 0): a diferencia de
-- transactions, esta fila no es un movimiento real y no afecta a
-- ningún balance, así que no necesita signo ni partida doble.
--
-- La consistencia entre category_id/to_account_id y type sigue el
-- mismo criterio estructural que transactions (una transferencia no
-- admite categoría, income/expense no admiten to_account_id), y la
-- consistencia entre category_id y account_id (que ambos pertenezcan
-- al mismo grupo) se impone con trigger, igual que en transactions —
-- ver justificación detallada allí.
-- =============================================================

CREATE TABLE payment_plans (
    id                 UUID                  PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id         UUID                  NOT NULL REFERENCES accounts (id) ON DELETE CASCADE,
    to_account_id      UUID                  REFERENCES accounts (id) ON DELETE SET NULL,
    category_id        UUID                  REFERENCES categories (id) ON DELETE SET NULL,
    type               transaction_type_enum NOT NULL,
    amount             BIGINT                NOT NULL CHECK (amount > 0),
    description        TEXT,
    next_due_date      DATE                  NOT NULL,
    end_date           DATE,
    is_recurring       BOOLEAN               NOT NULL DEFAULT FALSE,
    is_active          BOOLEAN               NOT NULL DEFAULT TRUE,
    frequency_interval INT                   CHECK (frequency_interval > 0),
    frequency_unit     frequency_unit_enum,
    created_by         UUID                  REFERENCES users (id) ON DELETE SET NULL,
    updated_by         UUID                  REFERENCES users (id) ON DELETE SET NULL,
    created_at         TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at         TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),

    -- Un plan recurrente necesita su periodicidad y, opcionalmente,
    -- una fecha de fin; uno puntual no admite ninguna de las dos —
    -- end_date sin is_recurring no tiene sentido (¿fin de qué
    -- repetición?).
    CONSTRAINT chk_recurring_fields CHECK (
        (is_recurring = TRUE AND frequency_interval IS NOT NULL AND frequency_unit IS NOT NULL)
        OR (is_recurring = FALSE AND frequency_interval IS NULL AND frequency_unit IS NULL AND end_date IS NULL)
    ),

    CONSTRAINT chk_end_date_after_due CHECK (
        end_date IS NULL OR end_date >= next_due_date
    ),

    CONSTRAINT chk_transfer_account CHECK (
        (type = 'transfer' AND to_account_id IS NOT NULL AND to_account_id <> account_id)
        OR (type <> 'transfer' AND to_account_id IS NULL)
    ),

    CONSTRAINT chk_transfer_no_category CHECK (
        type <> 'transfer' OR category_id IS NULL
    )
);

CREATE INDEX idx_payment_plans_account_id    ON payment_plans (account_id);
CREATE INDEX idx_payment_plans_next_due_date ON payment_plans (next_due_date) WHERE is_active = TRUE;

CREATE TRIGGER trg_payment_plans_set_updated_at
    BEFORE UPDATE ON payment_plans
    FOR EACH ROW
    EXECUTE FUNCTION set_updated_at();

CREATE OR REPLACE FUNCTION check_payment_plan_category_group()
RETURNS TRIGGER AS $$
DECLARE
    v_account_group  UUID;
    v_category_group UUID;
BEGIN
    IF NEW.category_id IS NOT NULL THEN
        SELECT group_id INTO v_account_group  FROM accounts   WHERE id = NEW.account_id;
        SELECT group_id INTO v_category_group FROM categories WHERE id = NEW.category_id;
        IF v_account_group IS DISTINCT FROM v_category_group THEN
            RAISE EXCEPTION 'La categoría debe pertenecer al mismo grupo que la cuenta.';
        END IF;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_check_payment_plan_category_group
    BEFORE INSERT OR UPDATE ON payment_plans
    FOR EACH ROW
    EXECUTE FUNCTION check_payment_plan_category_group();


-- =============================================================
-- TRANSACTIONS
-- El registro histórico real de movimientos — el corazón de la
-- aplicación. Cada fila afecta al balance de UNA sola cuenta, la
-- suya (account_id) — sin excepción, incluidas las transferencias.
--
-- Un income o un expense es una única fila: el signo de amount
-- indica su efecto (+ suma, - resta), impuesto por chk_amount_sign.
--
-- Una transferencia es SIEMPRE DOS filas — partida doble, no una
-- fila con dos cuentas: una en la cuenta de origen (amount
-- negativo) y otra en la cuenta de destino (amount positivo),
-- enlazadas por transfer_group_id (un identificador compartido por
-- las dos, no una autorreferencia de una fila a la otra). Esto es
-- lo que permite que "balance = suma de amount de mis filas" valga
-- para cualquier cuenta sin casos especiales, y que el listado de
-- una cuenta (WHERE account_id = :id) muestre tanto sus
-- transferencias salientes como las entrantes sin necesitar un OR
-- contra to_account_id — con el diseño anterior de una sola fila,
-- una cuenta destino no aparecía nunca en su propio listado.
--
-- to_account_id se mantiene en cada fila, pero ahora es solo
-- informativo (qué cuenta es la contraparte de esta pata) — el
-- cálculo de balance ya no lo usa.
--
-- Mantener las dos patas sincronizadas (importe con signo
-- invertido, misma fecha, mismas notas, mismo borrado lógico) es
-- responsabilidad de un trigger, trg_sync_transfer_pair, no de la
-- aplicación: así ni un UPDATE hecho a mano en psql puede
-- descuadrar el par.
--
-- deleted_at implementa borrado lógico: en un libro contable el
-- historial es el producto, así que una transacción se archiva
-- (con marca de cuándo) en vez de eliminarse físicamente. Borrar
-- (o restaurar) una pata de una transferencia borra (o restaura)
-- la otra, vía el mismo trg_sync_transfer_pair.
--
-- ocr_receipt_ref guarda, como texto, el identificador del
-- documento correspondiente en MongoDB cuando la transacción se
-- originó a partir de un recibo escaneado por OCR — sin relación
-- de clave foránea real, al ser un motor de base de datos distinto,
-- solo una convención de aplicación.
-- =============================================================

CREATE TABLE transactions (
    id                UUID                  PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id        UUID                  NOT NULL REFERENCES accounts (id) ON DELETE CASCADE,
    to_account_id     UUID                  REFERENCES accounts (id) ON DELETE SET NULL,
    category_id       UUID                  REFERENCES categories (id) ON DELETE SET NULL,
    payment_plan_id   UUID                  REFERENCES payment_plans (id) ON DELETE SET NULL,
    transfer_group_id UUID,
    amount            BIGINT                NOT NULL CHECK (amount <> 0),
    type              transaction_type_enum NOT NULL,
    date              DATE                  NOT NULL,
    notes             TEXT,
    ocr_receipt_ref   VARCHAR(64),
    deleted_at        TIMESTAMP WITH TIME ZONE,
    created_by        UUID                  REFERENCES users (id) ON DELETE SET NULL,
    updated_by        UUID                  REFERENCES users (id) ON DELETE SET NULL,
    created_at        TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),

    CONSTRAINT chk_transfer_no_category CHECK (
        type <> 'transfer' OR category_id IS NULL
    ),

    CONSTRAINT chk_transfer_to_account CHECK (
        (type = 'transfer' AND to_account_id IS NOT NULL AND to_account_id <> account_id)
        OR (type <> 'transfer' AND to_account_id IS NULL)
    ),

    -- Cada pata de una transferencia necesita saber a qué par
    -- pertenece; income/expense, al ser una única fila, no tienen
    -- con quién enlazarse.
    CONSTRAINT chk_transfer_group CHECK (
        (type = 'transfer' AND transfer_group_id IS NOT NULL)
        OR (type <> 'transfer' AND transfer_group_id IS NULL)
    ),

    -- transfer ya no exige amount > 0: con partida doble, la pata
    -- de origen es negativa y la de destino positiva, igual que
    -- expense/income — solo se exige que no sea cero.
    CONSTRAINT chk_amount_sign CHECK (
        (type = 'income'   AND amount > 0) OR
        (type = 'expense'  AND amount < 0) OR
        (type = 'transfer' AND amount <> 0)
    )
);

CREATE INDEX idx_transactions_account_id        ON transactions (account_id);
CREATE INDEX idx_transactions_date              ON transactions (date);
CREATE INDEX idx_transactions_payment_plan_id   ON transactions (payment_plan_id);
CREATE INDEX idx_transactions_type              ON transactions (type);
CREATE INDEX idx_transactions_transfer_group_id ON transactions (transfer_group_id)
    WHERE transfer_group_id IS NOT NULL;

CREATE TRIGGER trg_transactions_set_updated_at
    BEFORE UPDATE ON transactions
    FOR EACH ROW
    EXECUTE FUNCTION set_updated_at();

-- Aplica (o revierte) el efecto de una fila sobre el balance de SU
-- cuenta. p_sign vale +1 al aplicar una fila nueva/actual y -1 al
-- revertir una fila antigua/borrada. Ya no distingue por type: con
-- partida doble cada fila afecta a una sola cuenta, y el signo de
-- amount ya lleva codificado si suma o resta — sin el caso especial
-- de dos UPDATE que tenía el diseño de fila única para transfer.
CREATE OR REPLACE FUNCTION apply_transaction_effect(
    p_account_id UUID, p_amount BIGINT, p_sign INT
) RETURNS VOID AS $$
BEGIN
    UPDATE accounts SET balance = balance + (p_amount * p_sign) WHERE id = p_account_id;
END;
$$ LANGUAGE plpgsql;

-- INSERT aplica el efecto (salvo que nazca ya borrada, caso atípico
-- pero cubierto por seguridad); DELETE físico lo revierte solo si la
-- fila estaba activa (si ya estaba borrada lógicamente, su efecto ya
-- se revirtió en ese momento, y revertirlo otra vez descuadraría el
-- balance). UPDATE distingue explícitamente cuatro casos según cómo
-- cambia deleted_at, porque el borrado lógico (poner deleted_at) y la
-- restauración (quitarlo) también deben mover el balance, no solo los
-- cambios de importe con la fila siempre activa.
CREATE OR REPLACE FUNCTION trg_transactions_balance()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NEW.deleted_at IS NULL THEN
            PERFORM apply_transaction_effect(NEW.account_id, NEW.amount, 1);
        END IF;
        RETURN NEW;

    ELSIF TG_OP = 'DELETE' THEN
        IF OLD.deleted_at IS NULL THEN
            PERFORM apply_transaction_effect(OLD.account_id, OLD.amount, -1);
        END IF;
        RETURN OLD;

    ELSIF TG_OP = 'UPDATE' THEN
        IF OLD.deleted_at IS NULL AND NEW.deleted_at IS NOT NULL THEN
            -- Borrado lógico: revierte el efecto, no lo vuelve a aplicar.
            PERFORM apply_transaction_effect(OLD.account_id, OLD.amount, -1);

        ELSIF OLD.deleted_at IS NOT NULL AND NEW.deleted_at IS NULL THEN
            -- Restauración: aplica el efecto de la fila ya restaurada.
            PERFORM apply_transaction_effect(NEW.account_id, NEW.amount, 1);

        ELSIF OLD.deleted_at IS NULL AND NEW.deleted_at IS NULL THEN
            -- Sigue activa: cambio normal de importe.
            PERFORM apply_transaction_effect(OLD.account_id, OLD.amount, -1);
            PERFORM apply_transaction_effect(NEW.account_id, NEW.amount, 1);

        END IF;
        -- Si sigue borrada (edición de metadatos de una fila ya
        -- borrada), no se toca el balance: no estaba contribuyendo a él.
        RETURN NEW;
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_transactions_balance_update
    AFTER INSERT OR UPDATE OR DELETE ON transactions
    FOR EACH ROW
    EXECUTE FUNCTION trg_transactions_balance();

-- Mantiene sincronizadas las dos patas de una transferencia:
-- importe con signo invertido, misma fecha, mismas notas, mismo
-- borrado lógico. Se dispara sobre la fila que la aplicación edita
-- directamente y propaga el cambio a su pareja (localizada por
-- transfer_group_id); esa propagación es en sí misma un UPDATE, así
-- que sin guarda volvería a disparar este mismo trigger sobre la
-- fila original, en un ciclo infinito. pg_trigger_depth() > 1 corta
-- esa recursión: la fila original se edita a profundidad 1, la
-- propagación a su pareja ocurre a profundidad 2, y ahí se detiene
-- — la pareja no vuelve a propagar una tercera vez.
CREATE OR REPLACE FUNCTION sync_transfer_pair()
RETURNS TRIGGER AS $$
BEGIN
    IF pg_trigger_depth() > 1 THEN
        RETURN NEW;
    END IF;

    UPDATE transactions
    SET amount     = -NEW.amount,
        date       = NEW.date,
        notes      = NEW.notes,
        deleted_at = NEW.deleted_at,
        updated_by = NEW.updated_by
    WHERE transfer_group_id = NEW.transfer_group_id
      AND id <> NEW.id;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_sync_transfer_pair
    AFTER UPDATE ON transactions
    FOR EACH ROW
    WHEN (NEW.type = 'transfer')
    EXECUTE FUNCTION sync_transfer_pair();

-- Invariante de integridad cruzada que una FK normal no puede
-- expresar: la categoría de una transacción debe pertenecer al
-- mismo grupo que su cuenta. En la práctica solo se ejercita sobre
-- income/expense: category_id ya está prohibido en transfer por
-- chk_transfer_no_category.
CREATE OR REPLACE FUNCTION check_transaction_category_group()
RETURNS TRIGGER AS $$
DECLARE
    v_account_group  UUID;
    v_category_group UUID;
BEGIN
    IF NEW.category_id IS NOT NULL THEN
        SELECT group_id INTO v_account_group  FROM accounts   WHERE id = NEW.account_id;
        SELECT group_id INTO v_category_group FROM categories WHERE id = NEW.category_id;
        IF v_account_group IS DISTINCT FROM v_category_group THEN
            RAISE EXCEPTION 'La categoría debe pertenecer al mismo grupo que la cuenta.';
        END IF;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_check_transaction_category_group
    BEFORE INSERT OR UPDATE ON transactions
    FOR EACH ROW
    EXECUTE FUNCTION check_transaction_category_group();
