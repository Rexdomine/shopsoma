/**
 * Image Optimization Script
 * Compresses and converts hero images to WebP format for faster loading
 */

const sharp = require('sharp');
const fs = require('fs');
const path = require('path');

const HERO_IMAGES_DIR = path.join(__dirname, '../public/images/hero');
const QUALITY = 85; // Good balance between quality and size
const MAX_WIDTH = 800; // Max width for hero images

async function optimizeImage(inputPath, outputPath, format = 'jpeg') {
  try {
    const stats = fs.statSync(inputPath);
    const sizeMB = (stats.size / (1024 * 1024)).toFixed(2);

    console.log(`\nOptimizing: ${path.basename(inputPath)} (${sizeMB}MB)`);

    if (format === 'webp') {
      await sharp(inputPath)
        .resize(MAX_WIDTH, null, {
          withoutEnlargement: true,
          fit: 'inside'
        })
        .webp({ quality: QUALITY })
        .toFile(outputPath);
    } else {
      await sharp(inputPath)
        .resize(MAX_WIDTH, null, {
          withoutEnlargement: true,
          fit: 'inside'
        })
        .jpeg({ quality: QUALITY, progressive: true })
        .toFile(outputPath);
    }

    const newStats = fs.statSync(outputPath);
    const newSizeMB = (newStats.size / (1024 * 1024)).toFixed(2);
    const reduction = ((1 - newStats.size / stats.size) * 100).toFixed(1);

    console.log(`✅ Saved to: ${path.basename(outputPath)}`);
    console.log(`   Size: ${newSizeMB}MB (${reduction}% reduction)`);

  } catch (error) {
    console.error(`❌ Error optimizing ${inputPath}:`, error.message);
  }
}

async function optimizeAllImages() {
  console.log('🖼️  Starting image optimization...\n');

  // Get all jpg files in hero directory
  const files = fs.readdirSync(HERO_IMAGES_DIR)
    .filter(file => file.endsWith('.jpg') || file.endsWith('.jpeg'));

  if (files.length === 0) {
    console.log('No images found to optimize');
    return;
  }

  // Create optimized directory if it doesn't exist
  const optimizedDir = path.join(HERO_IMAGES_DIR, 'optimized');
  if (!fs.existsSync(optimizedDir)) {
    fs.mkdirSync(optimizedDir);
  }

  let totalOriginalSize = 0;
  let totalOptimizedSize = 0;

  for (const file of files) {
    const inputPath = path.join(HERO_IMAGES_DIR, file);
    const baseName = path.parse(file).name;

    // Generate both JPEG and WebP versions
    const jpegOutputPath = path.join(optimizedDir, `${baseName}.jpg`);
    const webpOutputPath = path.join(optimizedDir, `${baseName}.webp`);

    // Optimize to JPEG
    await optimizeImage(inputPath, jpegOutputPath, 'jpeg');

    // Convert to WebP
    await optimizeImage(inputPath, webpOutputPath, 'webp');

    // Track sizes
    const originalStats = fs.statSync(inputPath);
    const jpegStats = fs.statSync(jpegOutputPath);

    totalOriginalSize += originalStats.size;
    totalOptimizedSize += jpegStats.size;
  }

  const totalOriginalMB = (totalOriginalSize / (1024 * 1024)).toFixed(2);
  const totalOptimizedMB = (totalOptimizedSize / (1024 * 1024)).toFixed(2);
  const totalReduction = ((1 - totalOptimizedSize / totalOriginalSize) * 100).toFixed(1);

  console.log('\n📊 Summary:');
  console.log(`   Total original size: ${totalOriginalMB}MB`);
  console.log(`   Total optimized size: ${totalOptimizedMB}MB`);
  console.log(`   Total reduction: ${totalReduction}%`);
  console.log('\n✨ Optimization complete!');
  console.log(`   Optimized images saved to: ${optimizedDir}`);
  console.log('   Please replace the original images with the optimized ones.');
}

// Run the optimization
optimizeAllImages().catch(console.error);
