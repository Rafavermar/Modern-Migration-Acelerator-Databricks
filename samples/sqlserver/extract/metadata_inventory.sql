SET NOCOUNT ON;

DECLARE @source_system VARCHAR(100) = 'sql_server';
DECLARE @engine VARCHAR(100) = 'SQL Server';

WITH row_counts AS (
    SELECT
        object_id,
        SUM(row_count) AS row_count
    FROM sys.dm_db_partition_stats
    WHERE index_id IN (0, 1)
    GROUP BY object_id
),
dependencies AS (
    SELECT
        referencing_id,
        STRING_AGG(
            CONCAT(
                DB_NAME(),
                '.',
                COALESCE(referenced_schema_name, 'dbo'),
                '.',
                referenced_entity_name
            ),
            '|'
        ) WITHIN GROUP (ORDER BY referenced_schema_name, referenced_entity_name) AS depends_on
    FROM sys.sql_expression_dependencies
    WHERE referenced_entity_name IS NOT NULL
    GROUP BY referencing_id
)
SELECT
    @source_system AS source_system,
    DB_NAME() AS [database],
    SCHEMA_NAME(o.schema_id) AS [schema],
    CASE WHEN o.type = 'U' THEN o.name ELSE '' END AS [table],
    o.name AS object_name,
    CASE
        WHEN o.type = 'U' THEN 'table'
        WHEN o.type = 'V' THEN 'view'
        WHEN o.type = 'P' THEN 'stored_procedure'
        WHEN o.type IN ('FN', 'IF', 'TF') THEN 'function'
        ELSE LOWER(o.type_desc)
    END AS object_type,
    COALESCE(CONVERT(VARCHAR(30), rc.row_count), '') AS row_count,
    COALESCE(USER_NAME(o.principal_id), '') AS owner,
    '' AS criticality,
    @engine AS engine,
    '' AS location,
    '' AS format,
    COALESCE(d.depends_on, '') AS depends_on
FROM sys.objects AS o
LEFT JOIN row_counts AS rc
    ON o.object_id = rc.object_id
LEFT JOIN dependencies AS d
    ON o.object_id = d.referencing_id
WHERE o.type IN ('U', 'V', 'P', 'FN', 'IF', 'TF')
  AND o.is_ms_shipped = 0
ORDER BY object_type, [schema], object_name;
