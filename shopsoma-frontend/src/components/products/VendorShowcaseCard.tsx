import { Link } from 'react-router-dom';

interface VendorShowcaseCardProps {
  vendorName: string;
  vendorId: string;
  imageUrl: string;
  productCount: number;
}

export default function VendorShowcaseCard({
  vendorName,
  vendorId,
  imageUrl,
  productCount,
}: VendorShowcaseCardProps) {
  return (
    <Link
      to={`/vendors/${vendorId}`}
      className="group block"
    >
      {/* Image Container */}
      <div className="relative overflow-hidden aspect-[3/4] lg:aspect-[6/4] mb-4 bg-gray-100">
        {/* Vendor Image */}
        <img
          src={imageUrl}
          alt={vendorName}
          className="absolute inset-0 w-full h-full object-cover"
        />

        {/* Dark Overlay */}
        <div className="absolute inset-0 bg-black/30" />

        {/* Centered Vendor Name Overlay */}
        <div className="absolute inset-0 flex items-center justify-center">
          <h3 className="text-3xl lg:text-4xl font-serif font-light text-white uppercase tracking-[0.2em]">
            {vendorName}
          </h3>
        </div>

        {/* Hover overlay */}
        <div className="absolute inset-0 bg-primary/10 opacity-0 group-hover:opacity-100 transition-opacity duration-300" />
      </div>

      {/* Vendor Info - Outside Image */}
      <div className="space-y-1.5">
        {/* Related Designer Label */}
        <p className="text-[10px] font-ui uppercase tracking-[0.25em] text-primary">
          RELATED DESIGNER
        </p>

        {/* Vendor Name */}
        <h3 className="text-sm font-serif text-dark leading-snug line-clamp-2">
          {vendorName}
        </h3>

        {/* Product Count */}
        <div className="flex items-center gap-2">
          <span className="text-sm font-ui text-dark">
            {productCount} RELATED ITEMS
          </span>
        </div>
      </div>
    </Link>
  );
}
