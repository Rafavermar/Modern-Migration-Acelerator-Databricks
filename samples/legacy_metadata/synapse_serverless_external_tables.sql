CREATE EXTERNAL DATA SOURCE legacy_lake_source
WITH (
  LOCATION = 'abfss://legacy@storage.dfs.core.windows.net'
);

CREATE EXTERNAL FILE FORMAT parquet_format
WITH (
  FORMAT_TYPE = PARQUET
);

CREATE EXTERNAL TABLE ext.ExternalOrders (
  order_id BIGINT,
  customer_id BIGINT,
  order_date DATE,
  order_total DECIMAL(18, 2)
)
WITH (
  LOCATION = '/orders/',
  DATA_SOURCE = legacy_lake_source,
  FILE_FORMAT = parquet_format
);

CREATE EXTERNAL TABLE ext.ExternalCustomers (
  customer_id BIGINT,
  customer_name VARCHAR(200),
  customer_segment VARCHAR(50)
)
WITH (
  LOCATION = '/customers/',
  DATA_SOURCE = legacy_lake_source,
  FILE_FORMAT = parquet_format
);

CREATE VIEW rpt.vw_order_customer
AS
SELECT
  o.order_id,
  o.customer_id,
  c.customer_segment,
  o.order_total
FROM ext.ExternalOrders o
JOIN ext.ExternalCustomers c
  ON o.customer_id = c.customer_id;
