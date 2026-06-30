-- Cajas CHAPINA: productos de catálogo requeridos por la FK
-- DetallePedido.SKU -> Productos.SKU. Idempotente.
-- Aplicado en producción (Supabase) el 2026-06-30.

INSERT INTO "Productos" ("SKU", "Producto", "Precio") VALUES
  ('P0003', 'Value Box Chapina', 550),
  ('P0004', 'Premium Box Chapina', 675)
ON CONFLICT ("SKU") DO NOTHING;
