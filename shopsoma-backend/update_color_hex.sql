-- Update color_hex for existing product variants
UPDATE product_variants SET color_hex = '#FFFFFF' WHERE color = 'White';
UPDATE product_variants SET color_hex = '#000000' WHERE color = 'Black';
UPDATE product_variants SET color_hex = '#000080' WHERE color = 'Navy';
UPDATE product_variants SET color_hex = '#808080' WHERE color = 'Gray';
UPDATE product_variants SET color_hex = '#0000FF' WHERE color = 'Blue';
UPDATE product_variants SET color_hex = '#ADD8E6' WHERE color = 'Light Blue';
UPDATE product_variants SET color_hex = '#00008B' WHERE color = 'Dark Blue';
UPDATE product_variants SET color_hex = '#FFC0CB' WHERE color = 'Pink';
UPDATE product_variants SET color_hex = '#FF0000' WHERE color = 'Red';
UPDATE product_variants SET color_hex = '#008000' WHERE color = 'Green';
UPDATE product_variants SET color_hex = '#8B4513' WHERE color = 'Brown';
UPDATE product_variants SET color_hex = '#F0E68C' WHERE color = 'Khaki';
UPDATE product_variants SET color_hex = '#808000' WHERE color = 'Olive';
UPDATE product_variants SET color_hex = '#800020' WHERE color = 'Burgundy';
UPDATE product_variants SET color_hex = '#36454F' WHERE color = 'Charcoal';
