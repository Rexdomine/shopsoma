import { useCallback } from 'react';
import { useNavigate } from 'react-router-dom';

export interface ProfileMenuItem {
  label: string;
  route?: string;
  active?: boolean;
  onClick?: () => void;
}

interface ProfileMenuProps {
  items: ProfileMenuItem[];
  onNavigate?: (route: string) => void;
}

export default function ProfileMenu({ items, onNavigate }: ProfileMenuProps) {
  const navigate = useNavigate();

  const handleNavigate = useCallback(
    (route?: string) => {
      if (!route) return;
      if (onNavigate) {
        onNavigate(route);
      } else {
        navigate(route);
      }
    },
    [navigate, onNavigate]
  );

  const handleItemClick = useCallback((item: ProfileMenuItem) => {
    // If item has onClick handler, use it (for Sign Out)
    if (item.onClick) {
      item.onClick();
    } else if (item.route) {
      // Otherwise navigate to route
      handleNavigate(item.route);
    }
  }, [handleNavigate]);

  return (
    <nav className="w-full lg:w-1/4">
      <ul className="space-y-1 text-sm tracking-[0.15em] uppercase text-gray-400">
        {items.map((item) => {
          return (
            <li key={item.label}>
              <button
                type="button"
                onClick={() => handleItemClick(item)}
                className={`w-full text-left py-2 hover:text-primary ${item.active ? 'text-dark font-semibold' : ''}`}
              >
                {item.label}
              </button>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
