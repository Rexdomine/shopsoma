import { useEffect, useState } from 'react';
import { CalendarClock, Image as ImageIcon, Loader2, Save, Sparkles } from 'lucide-react';
import {
  getAdminComingSoonSettings,
  updateComingSoonSettings,
  type ComingSoonSettings as ComingSoonSettingsValue,
} from '../../services/settingsService';
import { useToast } from '../../hooks/useToast';
import ToastContainer from '../ui/ToastContainer';

const DEFAULT_IMAGE = '/images/hero/campaign/campaign-exterior-desktop.webp';

function toLocalInput(value: string | null): string {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  const offset = date.getTimezoneOffset();
  return new Date(date.getTime() - offset * 60_000).toISOString().slice(0, 16);
}

function toIso(value: string): string | null {
  return value ? new Date(value).toISOString() : null;
}

interface ComingSoonSettingsProps {
  onDirtyChange?: (dirty: boolean) => void;
  onBusyChange?: (busy: boolean) => void;
}

export default function ComingSoonSettings({ onDirtyChange, onBusyChange }: ComingSoonSettingsProps) {
  const { toasts, hideToast, success, error } = useToast();
  const [settings, setSettings] = useState<ComingSoonSettingsValue | null>(null);
  const [enabled, setEnabled] = useState(false);
  const [launchAt, setLaunchAt] = useState('');
  const [imageUrl, setImageUrl] = useState(DEFAULT_IMAGE);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    getAdminComingSoonSettings()
      .then((value) => {
        setSettings(value);
        setEnabled(value.enabled);
        setLaunchAt(toLocalInput(value.launch_at));
        setImageUrl(value.image_url || DEFAULT_IMAGE);
      })
      .catch((err: any) => error(err.response?.data?.detail || 'Failed to load launch settings', 'Error'))
      .finally(() => setLoading(false));
  }, [error]);

  const dirty = Boolean(settings) && (
    enabled !== settings?.enabled
    || launchAt !== toLocalInput(settings?.launch_at ?? null)
    || imageUrl !== (settings?.image_url || DEFAULT_IMAGE)
  );

  useEffect(() => {
    onDirtyChange?.(dirty);
    onBusyChange?.(saving);
    return () => {
      onDirtyChange?.(false);
      onBusyChange?.(false);
    };
  }, [dirty, saving, onBusyChange, onDirtyChange]);

  const save = async () => {
    if (enabled && launchAt && new Date(launchAt).getTime() <= Date.now()) {
      error('Choose a launch time in the future or clear the countdown.', 'Invalid launch time');
      return;
    }
    try {
      setSaving(true);
      const updated = await updateComingSoonSettings({
        enabled,
        launch_at: toIso(launchAt),
        image_url: imageUrl.trim() || DEFAULT_IMAGE,
      });
      setSettings(updated);
      setLaunchAt(toLocalInput(updated.launch_at));
      setImageUrl(updated.image_url);
      success('Coming-soon settings saved', 'Storefront updated');
    } catch (err: any) {
      error(err.response?.data?.detail || 'Failed to save coming-soon settings', 'Error');
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return <>
      <div className="flex items-center gap-3 rounded-2xl border border-slate-200 bg-white p-7 text-sm text-slate-600"><Loader2 className="h-5 w-5 animate-spin" />Loading launch settings…</div>
      <ToastContainer toasts={toasts} onClose={hideToast} />
    </>;
  }

  return (
    <>
      <div className="space-y-5">
      <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:p-7">
        <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
          <div className="max-w-2xl">
            <p className="text-xs font-bold uppercase tracking-[0.16em] text-[#105E53]">Storefront access</p>
            <h2 className="mt-1 flex items-center gap-2 text-2xl font-semibold text-slate-950"><Sparkles className="h-6 w-6 text-[#C79A3B]" />Coming soon mode</h2>
            <p className="mt-2 text-sm leading-6 text-slate-600">Temporarily replace the public storefront with a polished launch page while the admin dashboard remains available. The page opens automatically when the countdown reaches zero.</p>
          </div>
          <div className={`rounded-full px-3 py-1.5 text-xs font-bold ${enabled ? 'bg-amber-50 text-amber-800' : 'bg-emerald-50 text-emerald-800'}`}>
            {enabled ? 'Currently enabled' : 'Currently off'}
          </div>
        </div>

        <div className="mt-8 grid gap-6 lg:grid-cols-[minmax(0,1fr)_280px]">
          <div className="space-y-6">
            <label className="flex items-start gap-3 rounded-xl border border-slate-200 bg-slate-50 p-4 text-sm text-slate-700">
              <input type="checkbox" checked={enabled} onChange={(event) => setEnabled(event.target.checked)} className="mt-1 h-4 w-4 accent-[#105E53]" />
              <span><span className="block font-semibold text-slate-900">Show the coming-soon page</span><span className="mt-1 block text-xs leading-5 text-slate-500">Turn this off to return visitors to the normal ShopSoma storefront immediately.</span></span>
            </label>

            <label className="block max-w-md text-sm font-semibold text-slate-800" htmlFor="coming-soon-launch-at">
              <span className="flex items-center gap-2"><CalendarClock className="h-4 w-4 text-[#105E53]" />Launch countdown end</span>
              <input id="coming-soon-launch-at" type="datetime-local" value={launchAt} onChange={(event) => setLaunchAt(event.target.value)} className="mt-2 w-full rounded-lg border border-slate-300 px-3 py-2.5 text-slate-900" />
              <span className="mt-1 block text-xs font-normal text-slate-500">Uses your local time here and stores the launch moment in UTC. Clear it for an open-ended launch page.</span>
            </label>

            <label className="block max-w-xl text-sm font-semibold text-slate-800" htmlFor="coming-soon-image-url">
              <span className="flex items-center gap-2"><ImageIcon className="h-4 w-4 text-[#105E53]" />Launch image URL</span>
              <input id="coming-soon-image-url" type="url" value={imageUrl} onChange={(event) => setImageUrl(event.target.value)} className="mt-2 w-full rounded-lg border border-slate-300 px-3 py-2.5 text-slate-900" />
              <span className="mt-1 block text-xs font-normal text-slate-500">Defaults to the approved ShopSoma campaign image from the image drive. Use a hosted image URL if you want to swap it later.</span>
            </label>

            <div className="flex flex-wrap items-center gap-3 border-t border-slate-100 pt-5">
              <button type="button" onClick={save} disabled={!dirty || saving} className="inline-flex items-center gap-2 rounded-lg bg-[#105E53] px-4 py-2.5 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-40"><Save className="h-4 w-4" />{saving ? 'Saving…' : 'Save launch settings'}</button>
              {dirty && <span className="text-xs font-medium text-amber-700">Unsaved changes</span>}
            </div>
          </div>

          <div className="overflow-hidden rounded-2xl border border-[#105E53]/20 bg-[#123B38] shadow-inner">
            <img src={imageUrl || DEFAULT_IMAGE} alt="ShopSoma launch campaign preview" className="h-44 w-full object-cover opacity-90" onError={(event) => { event.currentTarget.src = DEFAULT_IMAGE; }} />
            <div className="p-4 text-white"><p className="text-[10px] font-bold uppercase tracking-[0.18em] text-[#E7C97A]">Preview</p><p className="mt-2 font-serif text-xl">A new way to shop is arriving.</p><p className="mt-2 text-xs leading-5 text-white/70">Visitors will see the countdown and this campaign image while launch mode is enabled.</p></div>
          </div>
        </div>
      </div>
      </div>
      <ToastContainer toasts={toasts} onClose={hideToast} />
    </>
  );
}
