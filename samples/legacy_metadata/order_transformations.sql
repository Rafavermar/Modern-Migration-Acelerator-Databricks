CREATE PROCEDURE dbo.usp_build_fact_orders
AS
BEGIN
  SELECT
    o.order_id,
    o.customer_id,
    c.customer_segment,
    o.order_total
  INTO mart.FactOrders
  FROM dbo.CustomerOrders o
  JOIN mart.DimCustomer c
    ON o.customer_id = c.customer_id;

  UPDATE mart.FactOrders
  SET order_total = 0
  WHERE order_total IS NULL;
END;
