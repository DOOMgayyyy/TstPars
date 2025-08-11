-- Таблица категорий (заполняется из Госаптеки)
CREATE TABLE medicine_types (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL UNIQUE
);

-- Таблица-каталог лекарств (заполняется из Госаптеки)
CREATE TABLE medicines (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL UNIQUE,
    description TEXT,
    image_url VARCHAR(255),
    type_id INTEGER,
    CONSTRAINT fk_medicine_type
        FOREIGN KEY(type_id)
        REFERENCES medicine_types(id)
        ON DELETE SET NULL
);

-- Справочник аптек
CREATE TABLE pharmacies (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    address VARCHAR(255) UNIQUE
);

-- Таблица с ценами и остатками в конкретных аптеках
CREATE TABLE pharmacy_prices (
    pharmacy_id INTEGER NOT NULL,
    medicine_id INTEGER NOT NULL,
    price NUMERIC(10, 2) NOT NULL CHECK (price >= 0),
    quantity INTEGER NOT NULL DEFAULT 0 CHECK (quantity >= 0),
    last_updated TIMESTAMPTZ DEFAULT NOW(),

    PRIMARY KEY (pharmacy_id, medicine_id),

    CONSTRAINT fk_pharmacy
        FOREIGN KEY(pharmacy_id)
        REFERENCES pharmacies(id)
        ON DELETE CASCADE,

    CONSTRAINT fk_medicine
        FOREIGN KEY(medicine_id)
        REFERENCES medicines(id)
        ON DELETE CASCADE
);

-- Создаем индексы для ускорения поиска
CREATE INDEX idx_medicines_name ON medicines(name);
CREATE INDEX idx_pharmacies_name ON pharmacies(name);