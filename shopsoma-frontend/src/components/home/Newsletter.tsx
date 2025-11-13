import { useState } from 'react';
import { CheckCircle } from 'lucide-react';

export default function Newsletter() {
  const [email, setEmail] = useState('');
  const [loading, setLoading] = useState(false);
  const [success, setSuccess] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!email) {
      setError('Please enter your email address');
      return;
    }

    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      setError('Please enter a valid email address');
      return;
    }

    setLoading(true);
    setError('');

    try {
      // TODO: Implement newsletter API call
      await new Promise((resolve) => setTimeout(resolve, 1000));

      setSuccess(true);
      setEmail('');

      // Reset success message after 3 seconds
      setTimeout(() => {
        setSuccess(false);
      }, 3000);
    } catch (err) {
      setError('Failed to subscribe. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <section className="py-20 lg:py-24 bg-gradient-to-br from-primary to-primary-dark relative overflow-hidden">
      {/* Decorative wave patterns */}
      <div className="absolute inset-0 opacity-[0.07]">
        <div className="absolute -top-20 -right-20 w-96 h-96 rounded-full border-[40px] border-white/20"></div>
        <div className="absolute top-1/2 -left-32 w-80 h-80 rounded-full border-[30px] border-white/20"></div>
        <div className="absolute -bottom-10 right-1/4 w-64 h-64 rounded-full border-[20px] border-white/20"></div>
      </div>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 relative z-10">
        <div className="grid lg:grid-cols-2 gap-12 items-center">
          {/* Left Content */}
          <div className="text-left">
            <h2 className="text-4xl lg:text-5xl font-display font-bold text-white mb-4 leading-tight">
              Join Our Newsletter
            </h2>
            <p className="text-lg font-body text-white/95 leading-relaxed">
              Simply enter your email address in the field below to receive the latest fashion and style updates from us.
            </p>
          </div>

          {/* Right Content - Form */}
          <div>
            {/* Success Message */}
            {success && (
              <div className="mb-4 inline-flex items-center gap-2 bg-white text-primary px-5 py-3 rounded-lg text-sm font-body font-medium shadow-lg">
                <CheckCircle className="w-5 h-5" />
                Successfully subscribed!
              </div>
            )}

            {/* Newsletter Form */}
            <form onSubmit={handleSubmit}>
              <div className="flex gap-0 bg-white rounded-lg shadow-xl overflow-hidden">
                <div className="flex items-center pl-5 pr-3 bg-white">
                  <svg className="w-5 h-5 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                  </svg>
                </div>
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="Your Emaill"
                  className="flex-1 px-2 py-4 bg-white font-body text-gray-700 placeholder-gray-400 focus:outline-none text-base"
                  disabled={loading}
                />
                <button
                  type="submit"
                  disabled={loading}
                  className="px-8 py-4 bg-primary text-white text-base font-body font-semibold hover:bg-primary-dark transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed whitespace-nowrap rounded-r-lg"
                >
                  {loading ? 'Subscribing...' : 'Subscribe'}
                </button>
              </div>

              {/* Error Message */}
              {error && (
                <p className="mt-3 text-white/90 text-sm">{error}</p>
              )}
            </form>
          </div>
        </div>
      </div>
    </section>
  );
}
