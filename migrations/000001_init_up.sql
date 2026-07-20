-- =============================================================
-- FinanzApp — Esquema inicial de base de datos
-- =============================================================
-- Aplicación de finanzas personales multiusuario. El dominio se
-- organiza alrededor de "grupos de cuentas" (account_groups): un
-- grupo puede representar a una persona sola o a varias personas
-- compartiendo finanzas (pareja, piso compartido, etc.), y todo
-- lo demás (cuentas, categorías, transacciones, planes de pago)
-- cuelga de un grupo, nunca directamente de un usuario. Esto es
-- lo que permite que varios usuarios vean y editen las mismas
-- cuentas sin duplicar datos.
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


-- =============================================================
-- USERS
-- Identidad de cada persona que usa la aplicación. Independiente
-- de a cuántos grupos pertenezca.
-- =============================================================

CREATE TABLE users (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email         VARCHAR(255) NOT NULL UNIQUE,
    password      VARCHAR(255) NOT NULL,
    name          VARCHAR(100) NOT NULL,
    created_at    TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_users_email ON users (email);


-- =============================================================
-- SESSIONS
-- Sesiones de autenticación activas por usuario. Se revocan
-- explícitamente (revoked = true) en vez de borrarse, para
-- mantener trazabilidad de accesos.
-- =============================================================

CREATE TABLE sessions (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id    UUID NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    revoked    BOOLEAN NOT NULL DEFAULT FALSE,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_sessions_user_id ON sessions (user_id);


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

    CONSTRAINT uq_group_member UNIQUE (group_id, user_id)
);

CREATE INDEX idx_group_members_group_id ON account_group_members (group_id);
CREATE INDEX idx_group_members_user_id  ON account_group_members (user_id);


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
-- La consistencia entre category_id y account_id (que ambos
-- pertenezcan al mismo grupo) se impone con trigger, igual que en
-- transactions — ver justificación detallada allí.
-- =============================================================

CREATE TABLE payment_plans (
    id                 UUID                PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id         UUID                NOT NULL REFERENCES accounts (id) ON DELETE CASCADE,
    to_account_id      UUID                REFERENCES accounts (id) ON DELETE SET NULL,
    category_id        UUID                REFERENCES categories (id) ON DELETE SET NULL,
    amount             BIGINT              NOT NULL CHECK (amount > 0),
    description        TEXT,
    next_due_date      DATE                NOT NULL,
    end_date           DATE,
    is_recurring       BOOLEAN             NOT NULL DEFAULT FALSE,
    is_active          BOOLEAN             NOT NULL DEFAULT TRUE,
    frequency_interval INT                 CHECK (frequency_interval > 0),
    frequency_unit     frequency_unit_enum,
    created_by         UUID                REFERENCES users (id) ON DELETE SET NULL,
    updated_by         UUID                REFERENCES users (id) ON DELETE SET NULL,
    created_at         TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at         TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),

    -- Un plan recurrente necesita su periodicidad definida; uno
    -- puntual, no.
    CONSTRAINT chk_recurring_fields CHECK (
        is_recurring = FALSE
        OR (frequency_interval IS NOT NULL AND frequency_unit IS NOT NULL)
    ),

    -- Una transferencia no puede tener origen y destino iguales.
    CONSTRAINT chk_transfer_account CHECK (
        to_account_id IS NULL OR account_id <> to_account_id
    )
);

CREATE INDEX idx_payment_plans_account_id    ON payment_plans (account_id);
CREATE INDEX idx_payment_plans_next_due_date ON payment_plans (next_due_date) WHERE is_active = TRUE;

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
-- aplicación. Cada fila afecta al balance de una o dos cuentas
-- (ver triggers más abajo).
--
-- Convención de signo sobre amount (impuesta por chk_amount_sign):
--   income   > 0  → incrementa el balance de account_id
--   expense  < 0  → decrementa el balance de account_id
--   transfer > 0  → magnitud que sale de account_id y entra en
--                   to_account_id (por eso transfer exige
--                   to_account_id y no admite category_id: una
--                   transferencia no es ni ingreso ni gasto
--                   categorizable, es un movimiento interno).
--
-- deleted_at implementa borrado lógico: en un libro contable el
-- historial es el producto, así que una transacción se archiva
-- (con marca de cuándo) en vez de eliminarse físicamente.
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

    CONSTRAINT chk_amount_sign CHECK (
        (type = 'income'   AND amount > 0) OR
        (type = 'expense'  AND amount < 0) OR
        (type = 'transfer' AND amount > 0)
    )
);

CREATE INDEX idx_transactions_account_id      ON transactions (account_id);
CREATE INDEX idx_transactions_date            ON transactions (date);
CREATE INDEX idx_transactions_payment_plan_id ON transactions (payment_plan_id);
CREATE INDEX idx_transactions_type            ON transactions (type);

-- Aplica el efecto de una transacción (o su reverso) sobre el
-- balance de las cuentas implicadas. p_sign vale +1 al aplicar
-- una fila nueva/actual y -1 al revertir una fila antigua/borrada.
CREATE OR REPLACE FUNCTION apply_transaction_effect(
    p_account_id UUID, p_to_account_id UUID, p_amount BIGINT,
    p_type transaction_type_enum, p_sign INT
) RETURNS VOID AS $$
BEGIN
    IF p_type IN ('income', 'expense') THEN
        UPDATE accounts SET balance = balance + (p_amount * p_sign) WHERE id = p_account_id;
    ELSIF p_type = 'transfer' THEN
        UPDATE accounts SET balance = balance - (p_amount * p_sign) WHERE id = p_account_id;
        UPDATE accounts SET balance = balance + (p_amount * p_sign) WHERE id = p_to_account_id;
    END IF;
END;
$$ LANGUAGE plpgsql;

-- INSERT aplica el efecto; DELETE lo revierte; UPDATE revierte el
-- efecto de la fila anterior y aplica el de la nueva (cubre tanto
-- un cambio de importe como un cambio de cuenta).
CREATE OR REPLACE FUNCTION trg_transactions_balance()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        PERFORM apply_transaction_effect(NEW.account_id, NEW.to_account_id, NEW.amount, NEW.type, 1);
        RETURN NEW;
    ELSIF TG_OP = 'DELETE' THEN
        PERFORM apply_transaction_effect(OLD.account_id, OLD.to_account_id, OLD.amount, OLD.type, -1);
        RETURN OLD;
    ELSIF TG_OP = 'UPDATE' THEN
        PERFORM apply_transaction_effect(OLD.account_id, OLD.to_account_id, OLD.amount, OLD.type, -1);
        PERFORM apply_transaction_effect(NEW.account_id, NEW.to_account_id, NEW.amount, NEW.type, 1);
        RETURN NEW;
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_transactions_balance_update
    AFTER INSERT OR UPDATE OR DELETE ON transactions
    FOR EACH ROW
    EXECUTE FUNCTION trg_transactions_balance();

-- Invariante de integridad cruzada que una FK normal no puede
-- expresar: la categoría de una transacción debe pertenecer al
-- mismo grupo que su cuenta.
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
