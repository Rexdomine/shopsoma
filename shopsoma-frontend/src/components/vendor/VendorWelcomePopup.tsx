import { ArrowRight, Sparkles, X } from 'lucide-react';

interface VendorWelcomePopupProps {
  isOpen: boolean;
  onClose: () => void;
  onCompleteProfile: () => void;
}

export default function VendorWelcomePopup({
  isOpen,
  onClose,
  onCompleteProfile,
}: VendorWelcomePopupProps) {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/45 px-4 backdrop-blur-sm">
      <div className="relative w-full max-w-xl overflow-hidden rounded-[28px] border border-[#d7e3df] bg-white shadow-[0_30px_80px_rgba(16,94,83,0.18)]">
        <button
          type="button"
          onClick={onClose}
          className="absolute right-4 top-4 rounded-full p-2 text-gray-400 transition hover:bg-gray-100 hover:text-gray-600"
          aria-label="Close welcome popup"
        >
          <X className="h-5 w-5" />
        </button>

        <div className="border-b border-[#e7efec] bg-[linear-gradient(135deg,#f4faf8_0%,#ffffff_58%,#eef7f4_100%)] px-8 py-7">
          <div className="mb-4 inline-flex h-14 w-14 items-center justify-center rounded-2xl bg-[#105E53] text-white shadow-lg shadow-[#105E53]/20">
            <Sparkles className="h-7 w-7" />
          </div>
          <p className="mb-2 text-xs font-semibold uppercase tracking-[0.28em] text-[#105E53]/75">
            Welcome to Shopsoma
          </p>
          <h2 className="max-w-md text-3xl font-display leading-tight text-[#12332c]">
            Complete your vendor profile to unlock your dashboard
          </h2>
        </div>

        <div className="space-y-6 px-8 py-7">
          <p className="text-sm leading-7 text-gray-600 font-ui">
            Before you can upload products, manage collections, or access the rest of your vendor tools,
            we need a few final details about your brand and payout setup.
          </p>

          <div className="rounded-2xl border border-[#dbe8e3] bg-[#f8fcfa] p-5">
            <p className="text-sm font-semibold text-[#12332c]">What happens next</p>
            <ul className="mt-3 space-y-2 text-sm text-gray-600 font-ui">
              <li>Complete your storefront and brand details</li>
              <li>Add your payout information</li>
              <li>Return to the dashboard with product tools unlocked</li>
            </ul>
          </div>

          <div className="flex flex-col gap-3 sm:flex-row">
            <button
              type="button"
              onClick={onCompleteProfile}
              className="inline-flex flex-1 items-center justify-center gap-2 rounded-full bg-[#105E53] px-6 py-3 text-sm font-semibold tracking-[0.08em] text-white transition hover:bg-[#0c4c45]"
            >
              Complete Profile
              <ArrowRight className="h-4 w-4" />
            </button>
            <button
              type="button"
              onClick={onClose}
              className="rounded-full border border-[#d7e3df] px-6 py-3 text-sm font-semibold tracking-[0.08em] text-[#105E53] transition hover:bg-[#f4faf8]"
            >
              Remind Me Later
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
