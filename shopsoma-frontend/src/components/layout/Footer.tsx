import { useState } from 'react';
import { Link } from 'react-router-dom';
import { subscribeToNewsletter } from '../../services/newsletterService';

export default function Footer() {
  const currentYear = new Date().getFullYear();
  const [email, setEmail] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

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

  return (
    <footer className="bg-[var(--color-page-bg)] border-t border-[#1E5053]">
      <div className="w-full px-8 py-10">
        <div className="grid grid-cols-5 gap-6 items-start max-w-[1400px] mx-auto">
          {/* Mailing List Section */}
          <div className="col-span-2 space-y-3">
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
                  className="bg-[#1E5053] text-white text-xs font-ui uppercase tracking-[0.2em] px-6 py-2 hover:opacity-90 transition-opacity whitespace-nowrap disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {isSubmitting ? 'JOINING...' : 'JOIN NOW'}
                </button>
              </div>
              {message && (
                <p
                  className={`text-xs font-ui ${
                    message.type === 'success' ? 'text-green-600' : 'text-red-600'
                  }`}
                >
                  {message.text}
                </p>
              )}
            </form>
          </div>

          {/* Customer Care */}
          <div className="space-y-3">
            <h4 className="text-xs font-ui uppercase tracking-[0.2em]" style={{ color: '#1E5053' }}>
              CUSTOMER CARE
            </h4>
            <ul className="space-y-2 text-sm font-serif" style={{ color: '#1E5053' }}>
              <li><Link to="/contact" className="hover:opacity-70">Contact us</Link></li>
              <li><Link to="/email" className="hover:opacity-70">Email us</Link></li>
              <li><Link to="/faqs" className="hover:opacity-70">FAQs</Link></li>
            </ul>
          </div>

          {/* Shipping & Returns */}
          <div className="space-y-3">
            <h4 className="text-xs font-ui uppercase tracking-[0.2em]" style={{ color: '#1E5053' }}>
              SHIPPING & RETURNS
            </h4>
            <ul className="space-y-2 text-sm font-serif" style={{ color: '#1E5053' }}>
              <li><Link to="/track" className="hover:opacity-70">Track an order</Link></li>
              <li><Link to="/returns" className="hover:opacity-70">Return an Order</Link></li>
              <li><Link to="/shipping" className="hover:opacity-70">Shipping times and Costs</Link></li>
            </ul>
          </div>

          {/* About Shopsoma */}
          <div className="space-y-3">
            <h4 className="text-xs font-ui uppercase tracking-[0.2em]" style={{ color: '#1E5053' }}>
              ABOUT SHOPSOMA
            </h4>
            <ul className="space-y-2 text-sm font-serif" style={{ color: '#1E5053' }}>
              <li><Link to="/about" className="hover:opacity-70">About us</Link></li>
              <li><Link to="/careers" className="hover:opacity-70">Careers and Openings</Link></li>
              <li><Link to="/collaborate" className="hover:opacity-70">Become a collaborator</Link></li>
            </ul>
          </div>

          {/* Policies - Hidden on mobile, keeps 5 columns */}
        </div>

        {/* Policies Row - Below on same plane */}
        <div className="grid grid-cols-5 gap-6 items-start max-w-[1400px] mx-auto mt-0">
          <div className="col-span-2"></div>
          <div></div>
          <div></div>
          <div className="space-y-3">
            <h4 className="text-xs font-ui uppercase tracking-[0.2em]" style={{ color: '#1E5053' }}>
              POLICIES
            </h4>
            <ul className="space-y-2 text-sm font-serif" style={{ color: '#1E5053' }}>
              <li><Link to="/privacy" className="hover:opacity-70">Privacy Policy</Link></li>
              <li><Link to="/terms" className="hover:opacity-70">Terms of Use</Link></li>
              <li><Link to="/shipping-policy" className="hover:opacity-70">Shipping Policy</Link></li>
            </ul>
          </div>
        </div>

        {/* Bottom Section */}
        <div className="mt-10 pt-6 text-xs font-ui" style={{ color: '#1E5053' }}>
          <span className="uppercase tracking-[0.2em]">SHOPSOMA {currentYear}</span>
        </div>
      </div>
    </footer>
  );
}
