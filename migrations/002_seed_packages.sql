-- Sabro Networks — Pre-Seeded Tariff Packages Migration 002
-- Required Standard Internet Packages:
-- 1. Sparko (5 Mbps)
-- 2. Veloza (15 Mbps)
-- 3. Nexora (20 Mbps)
-- 4. Zentro (25 Mbps)
-- 5. Voltra (35 Mbps)
-- 6. Astrix (50 Mbps)
-- 7. Maxora (75 Mbps)

INSERT INTO tariffs (name, speed_mb, price, description)
VALUES 
    ('Sparko', 5, 1200.0, 'Starter 5 Mbps FTTH package for basic browsing & messaging'),
    ('Veloza', 15, 1800.0, 'Fast 15 Mbps fiber package for streaming and family usage'),
    ('Nexora', 20, 2200.0, 'Ultra-smooth 20 Mbps fiber connection for HD streaming and work-from-home'),
    ('Zentro', 25, 2800.0, 'High performance 25 Mbps broadband for multi-device households'),
    ('Voltra', 35, 3500.0, 'Power user 35 Mbps lightning fiber for heavy downloading and gaming'),
    ('Astrix', 50, 4800.0, 'Premium 50 Mbps low-latency dedicated optical package for creators & streamers'),
    ('Maxora', 75, 6500.0, 'Ultimate 75 Mbps Gigabit-class business & power user FTTH connection')
ON CONFLICT DO NOTHING;
