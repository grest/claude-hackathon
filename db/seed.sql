-- Seed data matching data/sample_subscriptions.csv (8 rows)
INSERT INTO subscriptions (customer_id, plan, mrr, start_date, end_date, status) VALUES
    ('C001', 'pro',        99.00,  '2024-01-01', NULL,         'active'),
    ('C002', 'starter',    29.00,  '2024-01-15', '2024-03-15', 'churned'),
    ('C003', 'enterprise', 499.00, '2023-06-01', NULL,         'active'),
    ('C004', 'pro',        99.00,  '2024-02-01', '2024-04-01', 'churned'),
    ('C005', 'starter',    29.00,  '2024-03-01', NULL,         'active'),
    ('C006', 'enterprise', 499.00, '2023-12-01', '2024-02-28', 'churned'),
    ('C007', 'pro',        99.00,  '2024-01-01', NULL,         'active'),
    ('C008', 'starter',    29.00,  '2024-01-01', '2024-01-31', 'churned');

-- Seed data matching data/sample_events.csv (6 rows)
INSERT INTO events (event_id, customer_id, event_type, event_date, metadata) VALUES
    ('E001', 'C002', 'cancel_requested', '2024-03-10', 'reason=price'),
    ('E002', 'C004', 'cancel_requested', '2024-03-28', 'reason=competitor'),
    ('E003', 'C006', 'cancel_requested', '2024-02-20', 'reason=unused'),
    ('E004', 'C008', 'cancel_requested', '2024-01-25', 'reason=price'),
    ('E005', 'C001', 'plan_upgrade',     '2024-02-01', 'from=starter&to=pro'),
    ('E006', 'C003', 'plan_upgrade',     '2024-01-15', 'from=pro&to=enterprise');
