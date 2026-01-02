-- Demo schema + data for quick testing
CREATE TABLE IF NOT EXISTS branches (
  branch_id SERIAL PRIMARY KEY,
  branch_name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS orders (
  order_id SERIAL PRIMARY KEY,
  branch_id INT NOT NULL REFERENCES branches(branch_id),
  order_total NUMERIC(12,2) NOT NULL,
  status TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO branches(branch_name)
VALUES ('BKK'), ('CNX'), ('HKT'), ('KKN'), ('PTT')
ON CONFLICT (branch_name) DO NOTHING;

DO $$
DECLARE
  i INT;
  bid INT;
BEGIN
  FOR i IN 1..300 LOOP
    bid := (SELECT branch_id FROM branches ORDER BY random() LIMIT 1);
    INSERT INTO orders(branch_id, order_total, status, created_at)
    VALUES (
      bid,
      round((random()*5000 + 100)::numeric, 2),
      CASE WHEN random() < 0.85 THEN 'paid' ELSE 'cancelled' END,
      NOW() - (random()*40 || ' days')::interval
    );
  END LOOP;
END $$;
