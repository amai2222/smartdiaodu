-- 为默认司机（admin@test.com 登录后使用的 driver_id）绑定车牌 苏F18D03
UPDATE drivers
SET plate_number = '苏F18D03'
WHERE id = 'a0000001-0000-4000-8000-000000000001';
