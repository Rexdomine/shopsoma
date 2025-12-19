/**
 * Shop Soma Brand Pattern Component
 * S-knot repeating pattern for backgrounds and overlays
 * Usage: Apply with low opacity (10-20%) as per brand guidelines
 */

interface BrandPatternProps {
  opacity?: number;
  className?: string;
}

export default function BrandPattern({ opacity = 0.1, className = '' }: BrandPatternProps) {
  return (
    <div
      className={`absolute inset-0 pointer-events-none ${className}`}
      style={{ opacity }}
      aria-hidden="true"
    >
      <svg
        className="w-full h-full"
        xmlns="http://www.w3.org/2000/svg"
      >
        <defs>
          <pattern
            id="shop-soma-pattern"
            x="0"
            y="0"
            width="120"
            height="120"
            patternUnits="userSpaceOnUse"
          >
            {/* S-Knot Design - Two interwoven S shapes */}
            <path
              d="M40 30 Q 30 30, 30 40 T 40 50 Q 50 50, 50 40 T 40 30 M60 50 Q 70 50, 70 60 T 60 70 Q 50 70, 50 60 T 60 50"
              fill="none"
              stroke="#105E53"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
            <path
              d="M50 35 Q 55 35, 55 40 T 50 45 Q 45 45, 45 40 T 50 35 M70 55 Q 75 55, 75 60 T 70 65 Q 65 65, 65 60 T 70 55"
              fill="none"
              stroke="#105E53"
              strokeWidth="1.5"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </pattern>
        </defs>
        <rect width="100%" height="100%" fill="url(#shop-soma-pattern)" />
      </svg>
    </div>
  );
}

/**
 * Usage Examples:
 *
 * 1. As hero section background:
 *    <div className="relative">
 *      <BrandPattern opacity={0.15} />
 *      <div className="relative z-10">Content here</div>
 *    </div>
 *
 * 2. As section divider:
 *    <div className="relative h-24 bg-white">
 *      <BrandPattern opacity={0.2} />
 *    </div>
 *
 * 3. As product overlay:
 *    <div className="relative">
 *      <BrandPattern opacity={0.1} className="rounded-lg" />
 *      <div className="relative z-10">Product content</div>
 *    </div>
 */
