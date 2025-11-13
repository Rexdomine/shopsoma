/**
 * Main Layout Component
 * Wraps pages with Header and Footer
 */
import type { ReactNode } from 'react';
import Header from './Header';
import Footer from './Footer';

interface LayoutProps {
  children: ReactNode;
  showHeader?: boolean;
  showFooter?: boolean;
}

export default function Layout({
  children,
  showHeader = true,
  showFooter = true,
}: LayoutProps) {
  return (
    <div className="min-h-screen flex flex-col">
      {showHeader && <Header />}
      <main className="flex-grow">{children}</main>
      {showFooter && <Footer />}
    </div>
  );
}
