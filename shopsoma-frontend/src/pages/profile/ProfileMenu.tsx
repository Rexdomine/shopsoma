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
    <nav className="w-full lg:w-1/4 min-w-0">
      <ul className="flex flex-row lg:flex-col overflow-x-auto gap-1 lg:gap-0 lg:space-y-1 text-xs lg:text-sm tracking-[0.15em] uppercase text-gray-400 pb-2 lg:pb-0 border-b lg:border-b-0 border-gray-100 mb-4 lg:mb-0">
        {items.map((item) => {
          return (
            <li key={item.label} className="shrink-0 lg:shrink">
              <button
                type="button"
                onClick={() => handleItemClick(item)}
                className={`w-full text-left px-3 lg:px-0 py-2 rounded-lg lg:rounded-none whitespace-nowrap lg:whitespace-normal hover:text-primary transition-colors ${
                  item.active ? 'text-gray-900 bg-gray-100 lg:bg-transparent font-semibold' : ''
                }`}
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
