IF DB_ID('LegacySales') IS NULL
BEGIN
    CREATE DATABASE LegacySales;
END;
GO

USE LegacySales;
GO

IF SCHEMA_ID('mart') IS NULL
BEGIN
    EXEC('CREATE SCHEMA mart');
END;
GO

IF OBJECT_ID('dbo.CustomerOrders', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.CustomerOrders
    (
        order_id BIGINT NOT NULL,
        customer_id BIGINT NOT NULL,
        order_date DATE NOT NULL,
        order_total DECIMAL(18, 2) NULL,
        source_system VARCHAR(50) NOT NULL,
        CONSTRAINT PK_CustomerOrders PRIMARY KEY (order_id)
    );
END;
GO

IF OBJECT_ID('dbo.Customers', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.Customers
    (
        customer_id BIGINT NOT NULL,
        customer_name VARCHAR(200) NOT NULL,
        customer_segment VARCHAR(50) NULL,
        CONSTRAINT PK_Customers PRIMARY KEY (customer_id)
    );
END;
GO

IF NOT EXISTS (SELECT 1 FROM dbo.Customers WHERE customer_id = 1001)
BEGIN
    INSERT INTO dbo.Customers (customer_id, customer_name, customer_segment)
    VALUES
        (1001, 'Acme Industries', 'enterprise'),
        (1002, 'Northwind Retail', 'mid-market'),
        (1003, 'Contoso Online', 'digital');
END;
GO

IF NOT EXISTS (SELECT 1 FROM dbo.CustomerOrders WHERE order_id = 50001)
BEGIN
    INSERT INTO dbo.CustomerOrders (order_id, customer_id, order_date, order_total, source_system)
    VALUES
        (50001, 1001, '2025-01-15', 120000.00, 'erp'),
        (50002, 1001, '2025-02-20', 95000.50, 'erp'),
        (50003, 1002, '2025-03-01', 15000.25, 'commerce'),
        (50004, 1003, '2025-03-03', NULL, 'commerce');
END;
GO

CREATE OR ALTER VIEW mart.DimCustomer
AS
SELECT
    customer_id,
    customer_name,
    customer_segment
FROM dbo.Customers;
GO

CREATE OR ALTER VIEW mart.FactOrders
AS
SELECT
    o.order_id,
    o.customer_id,
    c.customer_segment,
    o.order_date,
    ISNULL(o.order_total, 0) AS order_total
FROM dbo.CustomerOrders AS o
INNER JOIN mart.DimCustomer AS c
    ON o.customer_id = c.customer_id;
GO

CREATE OR ALTER PROCEDURE dbo.usp_build_fact_orders
AS
BEGIN
    SET NOCOUNT ON;

    SELECT
        o.order_id,
        o.customer_id,
        c.customer_segment,
        o.order_total
    FROM dbo.CustomerOrders AS o
    INNER JOIN mart.DimCustomer AS c
        ON o.customer_id = c.customer_id;
END;
GO
