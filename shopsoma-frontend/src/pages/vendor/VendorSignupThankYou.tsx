import { Link } from 'react-router-dom';
import { ROUTES } from '../../config/constants';
import { ArrowRight } from 'lucide-react';

export default function VendorSignupThankYou() {
  return (
    <div className="min-h-screen bg-[var(--color-page-bg)] flex flex-col items-center justify-between py-12 px-6">
      <div className="flex flex-col items-center gap-4">
        <img src="/images/somalogo.svg" alt="Shopsoma" className="h-8 w-auto" />
      </div>

      <div className="flex flex-col items-center text-center gap-3">
        <h1 className="text-3xl sm:text-4xl font-display text-[#444]">Thank you for signing up!</h1>
        <p className="text-sm text-gray-600 font-ui">
          You’re on the list. We’ll contact you with our
          <br />
          decision in the next couple of days
        </p>
        <Link
          to={ROUTES.HOME}
          className="mt-4 inline-flex items-center gap-2 rounded-full bg-[#105E53] text-white px-5 py-3 text-sm font-ui hover:bg-[#0c4c45] transition"
        >
          Back to Shopsoma.com
          <ArrowRight className="h-4 w-4" />
        </Link>
      </div>

      <div className="flex items-center gap-6 text-xs text-gray-500 font-ui pb-4">
        <Link to="#" className="hover:text-[#105E53]">Terms and Conditions</Link>
        <Link to="#" className="hover:text-[#105E53]">Privacy Policy</Link>
      </div>
    </div>
  );
}
