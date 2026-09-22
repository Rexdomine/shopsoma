import { useState } from 'react';
import { Link } from 'react-router-dom';
import { subscribeToNewsletter } from '../../services/newsletterService';

export const FOOTER_SECTIONS = [
  { key: 'customer-care', title: 'Customer Care', links: [{ to: '/contact', label: 'Contact Us' }, { to: '/track', label: 'Track your order' }, { to: '/shipping', label: 'Shipping' }, { to: '/returns', label: 'Returns and Refunds' }, { to: '/faqs', label: 'FAQ' }] },
  { key: 'about', title: 'About ShopSoma', links: [{ to: '/about', label: 'About Us' }, { to: '/collaborate', label: 'Become a ShopSoma partner' }] },
  { key: 'policies', title: 'Policies', links: [{ to: '/terms', label: 'Terms of Use' }, { to: '/privacy', label: 'Privacy Policy' }, { to: '/cookies', label: 'Cookie Policy' }] },
] as const;

export default function Footer() {
  const currentYear = new Date().getFullYear();
  const [email, setEmail] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [openSection, setOpenSection] = useState<string | null>('customer-care');

  const handleNewsletterSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!email || !email.includes('@')) {
      setMessage({ type: 'error', text: 'Please enter a valid email address' });
      return;
    }

    setIsSubmitting(true);
    setMessage(null);

    try {
      await subscribeToNewsletter({ email });
      setMessage({ type: 'success', text: 'Successfully subscribed to our newsletter!' });
      setEmail('');
    } catch (error: any) {
      const errorMessage = error.response?.data?.detail || 'Failed to subscribe. Please try again.';
      setMessage({ type: 'error', text: errorMessage });
    } finally {
      setIsSubmitting(false);
    }
  };

  const sections = FOOTER_SECTIONS;

  const toggleSection = (key: string) => {
    setOpenSection((current) => (current === key ? null : key));
  };

  return (
    <footer className="bg-[var(--color-page-bg)] border-t border-[#1E5053]">
      <div className="w-full px-8 py-10">
        <div className="block lg:hidden max-w-[640px] mx-auto">
          <div className="space-y-6">
            <h3 className="text-xs font-ui uppercase tracking-[0.2em]" style={{ color: '#1E5053' }}>
              JOIN OUR MAILING LIST
            </h3>
            <p className="text-sm font-serif leading-relaxed" style={{ color: '#1E5053' }}>
              Subscribe to get special offers, free giveaways, and once-in-a-lifetime deals.
            </p>
            <form onSubmit={handleNewsletterSubmit} className="space-y-2">
              <div className="flex gap-0">
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="example@mail.com"
                  className="flex-1 border border-[#1E5053] bg-white px-3 py-2 text-sm font-ui focus:outline-none"
                  style={{ color: '#1E5053' }}
                  disabled={isSubmitting}
                  required
                />
                <button
                  type="submit"
                  disabled={isSubmitting}
                  className="bg-[#1E5053] text-white text-xs font-ui uppercase tracking-[0.3em] px-5"
                >
                  {isSubmitting ? '...' : 'Join Now'}
                </button>
              </div>
              {message && (
                <p className={`text-xs ${message.type === 'success' ? 'text-green-600' : 'text-red-600'}`}>
                  {message.text}
                </p>
              )}
            </form>
            <Link
              to="/vendor/signup"
              className="inline-flex items-center justify-center border border-[#1E5053] text-xs font-ui uppercase tracking-[0.3em] px-6 py-3"
              style={{ color: '#1E5053' }}
            >
              Sell on Shopsoma
            </Link>
          </div>

          <div className="mt-10 space-y-4">
            {sections.map((section) => {
              const isOpen = openSection === section.key;
              return (
                <div key={section.key} className="border-b border-[#1E5053] pb-4">
                  <button
                    type="button"
                    onClick={() => toggleSection(section.key)}
                    aria-expanded={isOpen}
                    aria-controls={`footer-${section.key}-links`}
                    className="w-full flex items-center justify-between text-left"
                  >
                    <span className="text-xs font-ui uppercase tracking-[0.25em]" style={{ color: '#1E5053' }}>
                      {section.title}
                    </span>
                    <span className={`transition-transform ${isOpen ? 'rotate-180' : ''}`}>
                      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#1E5053" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                        <polyline points="6 9 12 15 18 9" />
                      </svg>
                    </span>
                  </button>
                  {isOpen && (
                    <div id={`footer-${section.key}-links`} className="mt-3 space-y-2">
                      {section.links.map((link) => (
                        <Link
                          key={link.to}
                          to={link.to}
                          className="block text-sm font-serif"
                          style={{ color: '#1E5053' }}
                        >
                          {link.label}
                        </Link>
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          <div className="mt-10 text-xs font-ui uppercase tracking-[0.3em] text-center" style={{ color: '#1E5053' }}>
            Shopsoma {currentYear}
          </div>
        </div>

        <div className="hidden lg:block">
          <div className="max-w-7xl mx-auto">
            <div className="grid grid-cols-5 gap-8">
              {/* Newsletter */}
              <div className="col-span-2">
                <h3 className="text-sm font-ui uppercase tracking-[0.3em] mb-4 text-[#1E5053]">
                  Join Our Mailing List
                </h3>
                <p className="text-sm font-serif mb-4 text-[#1E5053]">
                  Subscribe to get special offers, free giveaways, and once-in-a-lifetime deals.
                </p>
                <form onSubmit={handleNewsletterSubmit}>
                  <div className="flex">
                    <input
                      type="email"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      placeholder="example@mail.com"
                      className="flex-1 border border-[#1E5053] p-2 text-sm font-ui focus:outline-none bg-white"
                      disabled={isSubmitting}
                      required
                    />
                    <button
                      type="submit"
                      disabled={isSubmitting}
                      className="bg-[#1E5053] text-white px-6 text-sm font-ui uppercase tracking-[0.2em]"
                    >
                      {isSubmitting ? '...' : 'Join Now'}
                    </button>
                  </div>
                  {message && (
                    <p className={`text-xs mt-2 ${message.type === 'success' ? 'text-green-600' : 'text-red-600'}`}>
                      {message.text}
                    </p>
                  )}
                </form>
                <div className="mt-4">
                  <Link
                    to="/vendor/signup"
                    className="inline-block border border-[#1E5053] px-6 py-2 text-xs font-ui uppercase tracking-[0.3em] text-[#1E5053] hover:bg-[#1E5053] hover:text-white transition"
                  >
                    Sell on Shopsoma
                  </Link>
                </div>
              </div>

              {sections.map((section) => <div key={section.key}>
                <h3 className="text-sm font-ui uppercase tracking-[0.3em] mb-4 text-[#1E5053]">{section.title}</h3>
                <ul className="space-y-2">{section.links.map((link) => <li key={link.to}><Link to={link.to} className="text-sm font-serif text-[#1E5053] hover:underline">{link.label}</Link></li>)}</ul>
              </div>)}
            </div>

            <div className="mt-8 border-t border-[#1E5053] pt-4 text-xs font-ui uppercase tracking-[0.3em] text-[#1E5053]">
              Shopsoma {currentYear}
            </div>
          </div>
        </div>
      </div>
    </footer>
  );
}
