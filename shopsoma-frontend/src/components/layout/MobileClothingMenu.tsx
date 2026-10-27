import { ChevronRight } from 'lucide-react';
import { Link } from 'react-router-dom';
import type { Category } from '../../types';

export default function MobileClothingMenu({ label, route, categories, onNavigate }: {
  label: string;
  route: string;
  categories: Category[];
  onNavigate: () => void;
}) {
  const clothing = categories.filter(category => category.is_active &&
    !/accessories|shoes/.test(category.slug));
  return <details className="group">
    <summary aria-label={label} className="flex justify-between items-center min-h-11 cursor-pointer list-none">
      Clothing<ChevronRight size={20} aria-hidden="true" className="group-open:rotate-90" />
    </summary>
    <ul className="pl-3 text-base">
      {clothing.map(category => <li key={category.id}>
        <Link className="flex items-center min-h-11" to={`${route}?category=${encodeURIComponent(category.slug)}`} onClick={onNavigate}>{category.name}</Link>
      </li>)}
    </ul>
  </details>;
}
