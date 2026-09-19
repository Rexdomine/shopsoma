import { useEffect, useMemo, useState } from 'react';
import { ArrowRight, Instagram, Mail } from 'lucide-react';
import { getComingSoonSettings, type ComingSoonSettings } from '../services/settingsService';

const DEFAULT_IMAGE = '/images/hero/campaign/campaign-exterior-desktop.webp';

type Countdown = { days: number; hours: number; minutes: number; seconds: number };

function getCountdown(launchAt: string | null): Countdown {
  const remaining = launchAt ? Math.max(0, new Date(launchAt).getTime() - Date.now()) : 0;
  const totalSeconds = Math.floor(remaining / 1000);
  return {
    days: Math.floor(totalSeconds / 86_400),
    hours: Math.floor((totalSeconds % 86_400) / 3_600),
    minutes: Math.floor((totalSeconds % 3_600) / 60),
    seconds: totalSeconds % 60,
  };
}

function pad(value: number) {
  return value.toString().padStart(2, '0');
}

interface ComingSoonProps {
  onReleased?: () => void;
}

export default function ComingSoon({ onReleased }: ComingSoonProps) {
  const [settings, setSettings] = useState<ComingSoonSettings | null>(null);
  const [countdown, setCountdown] = useState<Countdown>(() => getCountdown(null));

  useEffect(() => {
    let mounted = true;
    getComingSoonSettings().then((value) => {
      if (!mounted) return;
      setSettings(value);
      setCountdown(getCountdown(value.launch_at));
      if (!value.enabled) onReleased?.();
    }).catch(() => {
      if (!mounted) return;
      // Fail open: an unavailable settings endpoint must not take down the storefront.
      setSettings({ enabled: false, launch_at: null, image_url: DEFAULT_IMAGE });
      onReleased?.();
    });
    return () => { mounted = false; };
  }, [onReleased]);

  useEffect(() => {
    if (!settings?.enabled) return undefined;
    if (!settings.launch_at) {
      let mounted = true;
      const refresh = window.setInterval(() => {
        getComingSoonSettings().then((value) => {
          if (mounted && !value.enabled) {
            setSettings(value);
            onReleased?.();
          }
        }).catch(() => {
          // Keep the current coming-soon view if a background refresh fails.
        });
      }, 10_000);
      return () => {
        mounted = false;
        window.clearInterval(refresh);
      };
    }
    let mounted = true;
    const timer = window.setInterval(() => {
      const next = getCountdown(settings.launch_at);
      setCountdown(next);
      if (mounted && new Date(settings.launch_at as string).getTime() <= Date.now()) {
        setSettings((current: ComingSoonSettings | null) => current ? { ...current, enabled: false } : current);
        onReleased?.();
      }
    }, 1000);
    return () => {
      mounted = false;
      window.clearInterval(timer);
    };
  }, [settings, onReleased]);

  const launchLabel = useMemo(() => {
    if (!settings?.launch_at) return 'Launching soon';
    return new Date(settings.launch_at).toLocaleDateString(undefined, { month: 'long', day: 'numeric', year: 'numeric' });
  }, [settings?.launch_at]);

  if (!settings?.enabled) return null;

  const units = [
    ['Days', countdown.days],
    ['Hours', countdown.hours],
    ['Minutes', countdown.minutes],
    ['Seconds', countdown.seconds],
  ] as const;

  return (
    <main className="min-h-screen overflow-hidden bg-[#0e302d] text-white">
      <div className="mx-auto grid min-h-screen max-w-[1440px] lg:grid-cols-[0.92fr_1.08fr]">
        <section className="relative flex flex-col justify-between px-6 py-8 sm:px-10 lg:px-16 lg:py-12">
          <div className="absolute -left-40 top-1/3 h-96 w-96 rounded-full bg-[#C79A3B]/10 blur-3xl" aria-hidden="true" />
          <header className="relative flex items-center justify-between">
            <img src="/assets/email/somalogoemail.png" alt="ShopSoma" className="h-10 w-auto object-contain brightness-0 invert" />
            <span className="rounded-full border border-white/20 px-3 py-1 text-[10px] font-bold uppercase tracking-[0.18em] text-[#E7C97A]">Opening soon</span>
          </header>

          <div className="relative my-16 max-w-xl lg:my-0">
            <p className="text-xs font-bold uppercase tracking-[0.25em] text-[#E7C97A]">The next edit is almost here</p>
            <h1 className="mt-5 max-w-lg font-serif text-5xl leading-[0.98] tracking-[-0.04em] sm:text-7xl">A new way to shop is arriving.</h1>
            <p className="mt-6 max-w-md text-base leading-7 text-white/70 sm:text-lg">ShopSoma brings the most considered African fashion into one beautifully curated destination. We are putting the final touches on your next favourite find.</p>
            <div className="mt-10 flex items-center gap-3 text-sm text-white/70"><span className="h-px w-10 bg-[#C79A3B]" />{launchLabel}</div>

            <div className="mt-8 grid max-w-md grid-cols-4 gap-2 sm:gap-3" aria-label="Launch countdown" aria-live="polite">
              {units.map(([label, value]) => <div key={label} className="rounded-2xl border border-white/15 bg-white/[0.07] px-2 py-4 text-center backdrop-blur-sm sm:px-4"><span className="block font-serif text-3xl text-[#E7C97A] sm:text-4xl">{label === 'Days' ? value : pad(value)}</span><span className="mt-1 block text-[9px] font-bold uppercase tracking-[0.16em] text-white/50">{label}</span></div>)}
            </div>
          </div>

          <footer className="relative flex items-center justify-between border-t border-white/10 pt-5 text-xs text-white/50"><span>© ShopSoma</span><div className="flex items-center gap-4"><a href="mailto:hello@shopsoma.com" aria-label="Email ShopSoma" className="transition hover:text-[#E7C97A]"><Mail className="h-4 w-4" /></a><a href="https://instagram.com" aria-label="ShopSoma on Instagram" className="transition hover:text-[#E7C97A]"><Instagram className="h-4 w-4" /></a><span className="flex items-center gap-1 text-white/70">Stay close <ArrowRight className="h-3.5 w-3.5" /></span></div></footer>
        </section>

        <section className="relative min-h-[420px] lg:min-h-screen" aria-label="ShopSoma campaign image">
          <img src={settings.image_url || DEFAULT_IMAGE} alt="ShopSoma campaign storefront" className="absolute inset-0 h-full w-full object-cover" onError={(event) => { event.currentTarget.src = DEFAULT_IMAGE; }} />
          <div className="absolute inset-0 bg-gradient-to-t from-[#0e302d]/45 via-transparent to-transparent" aria-hidden="true" />
          <div className="absolute bottom-6 left-6 max-w-xs text-sm leading-6 text-white/80 sm:bottom-10 sm:left-10">Curated style, independent voices, and pieces worth keeping.</div>
        </section>
      </div>
    </main>
  );
}
