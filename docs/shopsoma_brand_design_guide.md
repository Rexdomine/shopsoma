# 🛍️ SHOP SOMA Brand Design Guide

**Brand Essence:**  
Shop Soma is a retail e-commerce platform connecting **African luxury designers** with global customers.  
Its mission is to make African fashion accessible worldwide, while empowering designers with global visibility.

---

## 🎯 Brand Objective

- Enable customers globally to **shop African luxury designs** seamlessly.
- Provide African designers a **global storefront**.
- Build a platform that communicates **elegance, authenticity, and connectivity**.

---

## 🔗 Logo System

### Logo Mark
- The mark features **two interwoven “S” shapes** forming a **knot or rope link**.
- This represents **unity**, **connection**, and **craftsmanship**, echoing the platform’s goal of binding designers and customers.

### Word Mark
- Uses the **brand display font** — **Lao MN**.
- Always maintain **consistent spacing** and proportions relative to the logo mark.
- Do not distort, recolor, or add shadows to the logo.

---

## 🎨 Color Palette

| Color | Hex Code | Description | Usage |
|--------|-----------|-------------|--------|
| **Green** | `#105E53` | Core brand color representing growth, authenticity, and African roots | Primary Buttons, Links, Icons |
| **Dark Grey** | `#454444` | Neutral contrast tone | Text, Subheadings, Banners |
| **Light Grey** | `#B0B0B0` | Supporting neutral color | Backgrounds, borders, inactive states |

### Gradient
Used subtly in backgrounds or hero sections to bring depth and premium feel.  
Avoid strong transitions—keep gradients **soft and elegant**.

---

## 🧵 Pattern Usage

The repeating pattern derived from the **S-knot** should be used as:
- **Watermark backgrounds**
- **Subtle section dividers**
- **Product display overlays**

Opacity should stay below **20%** to maintain minimalism.

---

## ✍️ Typography

| Type | Font | Use |
|------|------|-----|
| **Primary / Display Typeface** | *Lao MN* | Headlines, Logo, Key labels |
| **Secondary Typeface** | *Montserrat* | Body text, Captions, Descriptions |

### Font Rules
- Use **Lao MN** for impactful titles and hero sections.  
- Use **Montserrat** (Regular/Medium) for all body and interface text.
- Maintain consistent **line height** (1.5× font size) and **letter spacing** (+1px for readability).

---

## 🖼️ Imagery Guidelines

**Style:**  
Clean, editorial, and modern. Use **white or neutral backgrounds** to highlight product quality.  

**Photography Direction:**
- Focus on product craftsmanship and detail.
- Use **natural light** or balanced studio lighting.
- Include African textures and patterns subtly, never overpowering the product.

**Image Ratios:**
- Product thumbnails: **1:1 (square)**
- Banners: **16:9**
- Hero images: **Full-width, 1920×1080 minimum**

---

## ✅ Correct Logo Usage

- Maintain **minimum clear space** around the logo equal to the height of the “S”.
- Logo can appear:
  - Green on white
  - White on dark background
- Avoid gradients, rotations, or outlines on the logo.

### Incorrect Usage
- Don’t change color combinations.
- Don’t stretch, rotate, or add effects.
- Don’t overlay on busy backgrounds.

---

## 💻 UI/UX Implementation Guide

For web developers & AI-based design automation:

1. **Primary Brand Color:** `#105E53`
2. **Accent Colors:** `#454444`, `#B0B0B0`
3. **Primary Font:** Lao MN (import via `@font-face`)
4. **Body Font:** Montserrat (Google Fonts)
5. **Button Design:**
   ```css
   .btn-primary {
     background-color: #105E53;
     color: white;
     border-radius: 8px;
     padding: 12px 24px;
     font-family: 'Montserrat', sans-serif;
     font-weight: 600;
   }
   .btn-primary:hover {
     opacity: 0.9;
   }
   ```
6. **Background Pattern:** Apply subtle 10–20% opacity “S-knot” texture as repeating background SVG.
7. **Heading hierarchy:**
   ```css
   h1 { font-family: 'Lao MN'; font-size: 2.5rem; }
   h2 { font-family: 'Lao MN'; font-size: 1.8rem; }
   p, span, li { font-family: 'Montserrat'; font-size: 1rem; line-height: 1.5; }
   ```

---

## 🧱 Component Design Tokens (for Tailwind / Design Systems)

| Token | Value | Description |
|--------|--------|-------------|
| `--color-primary` | `#105E53` | Brand Green |
| `--color-dark` | `#454444` | Text / Contrast |
| `--color-light` | `#B0B0B0` | Background |
| `--font-display` | `'Lao MN', serif` | Titles & logo |
| `--font-body` | `'Montserrat', sans-serif` | Body text |

---

## 📱 Responsive & Layout Rules

- Mobile-first design approach (375px → 1440px)
- Use **grid layouts** with **white space** for premium feel.
- Maintain **consistent padding (24px–32px)** across sections.
- Product cards use shadows at **5–10% opacity** for subtle depth.

---

## 📦 Brand Application Examples

### Mockups & Branding
- Keep minimalistic, elegant design.
- Use brand green on packaging, call-to-actions, and icons.
- Apply grey and white for product-neutral areas.

### Social Media
- Use consistent color overlays and logo watermark.
- Maintain tone of **elegance + African craftsmanship**.

---

## 🧩 Implementation Notes for AI Tools

When generating layouts, components, or styles:
- Use the **brand palette and typography** defined above.
- Always apply **Lao MN** for main headings and **Montserrat** for text.
- Apply the **S-knot pattern** as a background motif for banners or hero sections.
- Maintain **elegant whitespace and contrast** to reflect luxury.
- Focus on **minimalist elegance**, not bold color blocking.

---

## 🏁 Brand Keywords
> African | Luxury | Connected | Minimal | Elegant | Global | Authentic | Premium

---

**Document prepared for:** Shopsoma Web Development Team  
**Version:** v1.0 — Brand Developer Reference  
**Last Updated:** November 2025  
**Source:** Official *Shop Soma Brand Guide.pdf*
