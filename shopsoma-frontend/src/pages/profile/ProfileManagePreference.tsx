import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import Layout from '../../components/layout/Layout';
import { ROUTES } from '../../config/constants';
import ProfileMenu from './ProfileMenu';
import { getPreferences, updatePreferences, getPreferenceOptions } from '../../services/preferenceService';
import type { Currency } from '../../utils/pricing';
import { usePreferenceStore } from '../../store/preferenceStore';

export default function ProfileManagePreference() {
  const navigate = useNavigate();
  const [interest, setInterest] = useState<'womenswear' | 'menswear'>('womenswear');
  const [currency, setCurrency] = useState<Currency>('NGN');
  const [language, setLanguage] = useState('English');
  const [designerSearch, setDesignerSearch] = useState('');
  const [designerLetter, setDesignerLetter] = useState('');
  const [categorySearch, setCategorySearch] = useState('');
  const [designerOptions, setDesignerOptions] = useState<string[]>([]);
  const [categoryOptions, setCategoryOptions] = useState<string[]>([]);
  const [designers, setDesigners] = useState<string[]>([]);
  const [categories, setCategories] = useState<string[]>([]);
  const [toast, setToast] = useState(false);
  const [loadingPrefs, setLoadingPrefs] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const setGlobalCurrency = usePreferenceStore((state) => state.setCurrency);
  const setGlobalInterest = usePreferenceStore((state) => state.setInterest);
  const setGlobalDesigners = usePreferenceStore((state) => state.setDesigners);
  const setGlobalCategories = usePreferenceStore((state) => state.setCategories);

  const menuItems = [
    { label: 'Account Details', route: ROUTES.PROFILE },
    { label: 'Password', route: ROUTES.PROFILE_PASSWORD },
    { label: 'Order History', route: ROUTES.PROFILE_ORDERS },
    { label: 'Address', route: ROUTES.PROFILE_ADDRESS },
    { label: 'Return', route: ROUTES.PROFILE_RETURNS },
    { label: 'Wishlist', route: ROUTES.PROFILE_WISHLIST },
    { label: 'Newsletter', route: ROUTES.PROFILE_NEWSLETTER },
    { label: 'Manage Preference', route: ROUTES.PROFILE_MANAGE_PREFERENCE, active: true },
    { label: 'Payments', route: ROUTES.PROFILE_PAYMENTS },
    { label: 'Sign Out' },
  ];

  const designerPool = useMemo(() => {
    const values = new Set<string>(designerOptions);
    designers.forEach((name) => values.add(name));
    return Array.from(values).sort((a, b) => a.localeCompare(b));
  }, [designerOptions, designers]);

  const filteredDesigners = useMemo(() => {
    let result = designerPool;
    if (designerLetter) {
      result = result.filter((item) => item.toLowerCase().startsWith(designerLetter.toLowerCase()));
    }
    if (designerSearch.trim()) {
      result = result.filter((item) => item.toLowerCase().includes(designerSearch.toLowerCase()));
    }
    return result;
  }, [designerPool, designerLetter, designerSearch]);

  const categoryPool = useMemo(() => {
    const values = new Set<string>(categoryOptions);
    categories.forEach((name) => values.add(name));
    return Array.from(values).sort((a, b) => a.localeCompare(b));
  }, [categoryOptions, categories]);

  const filteredCategories = useMemo(() => {
    if (!categorySearch.trim()) return categoryPool;
    return categoryPool.filter((item) => item.toLowerCase().includes(categorySearch.toLowerCase()));
  }, [categoryPool, categorySearch]);

  const handleCurrencyChange = (value: string) => {
    setCurrency(value as Currency);
  };

  useEffect(() => {
    let isMounted = true;
    const loadPreferencesAndOptions = async () => {
      try {
        setLoadingPrefs(true);
        const [prefsResult, optionsResult] = await Promise.allSettled([
          getPreferences(),
          getPreferenceOptions(),
        ]);

        if (!isMounted) return;

        if (prefsResult.status === 'fulfilled') {
          const data = prefsResult.value;
          const resolvedInterest = data.interest === 'menswear' ? 'menswear' : 'womenswear';
          const resolvedCurrency = data.preferredCurrency?.toUpperCase() === 'USD' ? 'USD' : 'NGN';
          setInterest(resolvedInterest);
          setCurrency(resolvedCurrency);
          setLanguage(data.preferredLanguage ?? 'English');
          setDesigners(data.favoriteDesigners ?? []);
          setCategories(data.favoriteCategories ?? []);
          setGlobalInterest(resolvedInterest);
          setGlobalCurrency(resolvedCurrency);
          setGlobalDesigners(data.favoriteDesigners ?? []);
          setGlobalCategories(data.favoriteCategories ?? []);
          setError('');
        } else {
          setError('Failed to load preferences. Please try again.');
        }

        if (optionsResult.status === 'fulfilled') {
          const designerNames = optionsResult.value.designers
            .map((item) => item.name?.trim())
            .filter((name): name is string => Boolean(name))
            .sort((a, b) => a.localeCompare(b));
          const categoryNames = optionsResult.value.categories
            .map((item) => item.name?.trim())
            .filter((name): name is string => Boolean(name))
            .sort((a, b) => a.localeCompare(b));
          setDesignerOptions(designerNames);
          setCategoryOptions(categoryNames);
        } else {
          setError((prev) => prev || 'Failed to load preference options. Please try again.');
        }
      } catch (err) {
        if (isMounted) {
          setError('Failed to load preferences. Please try again.');
        }
      } finally {
        if (isMounted) {
          setLoadingPrefs(false);
        }
      }
    };

    loadPreferencesAndOptions();
    return () => {
      isMounted = false;
    };
  }, [setGlobalCurrency, setGlobalInterest]);

  const toggleSelection = (value: string, setFn: React.Dispatch<React.SetStateAction<string[]>>) => {
    setFn((prev) => (prev.includes(value) ? prev.filter((item) => item !== value) : [...prev, value]));
  };

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError('');
    setSubmitting(true);
    try {
      await updatePreferences({
        interest,
        preferredLanguage: language,
        preferredCurrency: currency,
        favoriteDesigners: designers,
        favoriteCategories: categories,
      });
      setGlobalInterest(interest);
      setGlobalCurrency(currency);
      setGlobalDesigners(designers);
      setGlobalCategories(categories);
      setToast(true);
      setTimeout(() => setToast(false), 3500);
    } catch (err: any) {
      const message = err?.response?.data?.detail || 'Failed to update preferences. Please try again.';
      setError(message);
    } finally {
      setSubmitting(false);
    }
  };

  const clearDesigners = () => setDesigners([]);
  const clearCategories = () => setCategories([]);

  return (
    <Layout>
      {toast && (
        <div className="fixed top-0 inset-x-0 z-50 bg-primary text-white shadow-md">
          <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-3 text-center text-sm">
            <p className="font-semibold uppercase tracking-[0.3em]">Manage Preference</p>
            <p className="text-white/90">Preferences updated successfully</p>
          </div>
        </div>
      )}
      <div className="bg-white">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-10 lg:py-16 flex flex-col gap-10 lg:flex-row">
          <ProfileMenu items={menuItems} onNavigate={(route) => navigate(route)} />
          <section className="flex-1">
            <header className="mb-8">
              <p className="text-xs uppercase tracking-[0.3em] text-gray-400">Manage Preference</p>
              {error && <p className="text-sm text-red-600 mt-2">{error}</p>}
            </header>
            {loadingPrefs ? (
              <div className="py-12 text-sm text-gray-500">Loading preferences...</div>
            ) : (
              <form onSubmit={handleSubmit} className="space-y-8">
              <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
                <div className="space-y-4 lg:col-span-1">
                  <p className="text-xs uppercase tracking-[0.3em] text-gray-400">I’m most interested in</p>
                  <div className="flex gap-6">
                    <label className="flex items-center gap-2 text-sm text-gray-700">
                      <input
                        type="radio"
                        name="interest"
                        value="womenswear"
                        checked={interest === 'womenswear'}
                        onChange={() => setInterest('womenswear')}
                      />
                      Womenswear
                    </label>
                    <label className="flex items-center gap-2 text-sm text-gray-700">
                      <input
                        type="radio"
                        name="interest"
                        value="menswear"
                        checked={interest === 'menswear'}
                        onChange={() => setInterest('menswear')}
                      />
                      Menswear
                    </label>
                  </div>
                </div>
                <DropdownField
                  label="Preferred Language"
                  value={language}
                  onChange={setLanguage}
                  options={[
                    { label: 'English', value: 'English' },
                    { label: 'French', value: 'French' },
                    { label: 'Spanish', value: 'Spanish' },
                  ]}
                />
                <DropdownField
                  label="Preferred Currency"
                  value={currency}
                  onChange={handleCurrencyChange}
                  options={[
                    { label: 'NGN - Nigerian Naira', value: 'NGN' },
                    { label: 'USD - United States Dollar', value: 'USD' },
                  ]}
                />
              </div>

              <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
                <SelectionPanel
                  title="Favorite Designers"
                  search={designerSearch}
                  onSearch={setDesignerSearch}
                  items={filteredDesigners}
                  selected={designers}
                  onToggle={(value) => toggleSelection(value, setDesigners)}
                  alphabetActive={designerLetter}
                  onLetterChange={setDesignerLetter}
                />
                <SelectedList
                  title="Selected Designers"
                  items={designers}
                  onClear={clearDesigners}
                  onRemove={(value) => toggleSelection(value, setDesigners)}
                />
              </div>

              <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
                <SelectionPanel
                  title="Favorite Categories"
                  search={categorySearch}
                  onSearch={setCategorySearch}
                  items={filteredCategories}
                  selected={categories}
                  onToggle={(value) => toggleSelection(value, setCategories)}
                />
                <SelectedList
                  title="Selected Categories"
                  items={categories}
                  onClear={clearCategories}
                  onRemove={(value) => toggleSelection(value, setCategories)}
                />
              </div>

              <button
                type="submit"
                disabled={submitting}
                className="px-8 py-3 bg-primary text-white rounded-sm text-xs font-semibold uppercase tracking-[0.3em] hover:bg-primary-dark transition disabled:opacity-60"
              >
                {submitting ? 'Saving...' : 'Update Preference'}
              </button>
              </form>
            )}
          </section>
        </div>
      </div>
    </Layout>
  );
}

interface DropdownOption {
  label: string;
  value: string;
}

interface DropdownFieldProps {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: DropdownOption[];
}

function DropdownField({ label, value, onChange, options }: DropdownFieldProps) {
  const [open, setOpen] = useState(false);

  return (
    <div className="space-y-1 relative">
      <p className="text-xs uppercase tracking-[0.3em] text-gray-400">{label}</p>
      <button
        type="button"
        onClick={() => setOpen((prev) => !prev)}
        className={`w-full border rounded-sm px-3 py-2 text-sm flex items-center justify-between transition focus:outline-none ${
          open ? 'border-primary' : 'border-gray-300 hover:border-primary/70'
        }`}
      >
        <span className="text-gray-900">{value || 'Select option'}</span>
        <svg
          className={`w-4 h-4 text-primary transition-transform ${open ? 'rotate-180' : ''}`}
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
          viewBox="0 0 24 24"
        >
          <path d="M6 9l6 6 6-6" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>
      {open && (
        <div className="absolute mt-1 w-full bg-white border border-gray-200 rounded-sm shadow-2xl z-10">
          {options.map((option) => (
            <button
              key={option.value}
              type="button"
              onClick={() => {
                onChange(option.value);
                setOpen(false);
              }}
              className={`w-full text-left px-4 py-2 text-sm transition ${
                option.value === value ? 'bg-primary/10 text-primary font-semibold' : 'hover:bg-gray-50 text-gray-700'
              }`}
            >
              {option.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

interface SelectionPanelProps {
  title: string;
  search: string;
  onSearch: (value: string) => void;
  items: string[];
  selected: string[];
  onToggle: (value: string) => void;
  alphabetActive?: string;
  onLetterChange?: (letter: string) => void;
}

function SelectionPanel({ title, search, onSearch, items, selected, onToggle, alphabetActive, onLetterChange }: SelectionPanelProps) {
  const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'.split('');

  return (
    <div className="space-y-4">
      <p className="text-xs uppercase tracking-[0.3em] text-gray-400">{title}</p>
      <div className="relative">
        <svg
          className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
          viewBox="0 0 24 24"
        >
          <path d="m21 21-4.35-4.35m0-6.65a7 7 0 1 1-14 0 7 7 0 0 1 14 0Z" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
        <input
          type="text"
          value={search}
          onChange={(event) => onSearch(event.target.value)}
          className="w-full border border-gray-300 rounded-sm pl-9 pr-3 py-2 text-sm focus:outline-none focus:border-primary"
          placeholder={`Search ${title.toLowerCase()}`}
        />
      </div>
      {onLetterChange && (
        <div className="flex flex-wrap gap-2 text-[11px] uppercase tracking-[0.2em] text-gray-400">
          {alphabet.map((letter) => (
            <button
              key={letter}
              type="button"
              onClick={() => onLetterChange(letter === alphabetActive ? '' : letter)}
              className={`px-1 ${
                alphabetActive === letter ? 'text-primary font-semibold' : 'hover:text-primary'
              }`}
            >
              {letter}
            </button>
          ))}
        </div>
      )}
      <div className="space-y-2 max-h-64 overflow-y-auto pr-2">
        {items.map((item) => (
          <label key={item} className="flex items-center gap-2 text-sm text-gray-700">
            <input type="checkbox" checked={selected.includes(item)} onChange={() => onToggle(item)} />
            {item}
          </label>
        ))}
        {items.length === 0 && <p className="text-xs text-gray-400">No matches</p>}
      </div>
    </div>
  );
}

interface SelectedListProps {
  title: string;
  items: string[];
  onClear: () => void;
  onRemove?: (value: string) => void;
}

function SelectedList({ title, items, onClear, onRemove }: SelectedListProps) {
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-xs uppercase tracking-[0.3em] text-gray-400">{title}</p>
        <button type="button" onClick={onClear} className="text-xs text-primary hover:underline">
          Remove all
        </button>
      </div>
      <div className="min-h-[200px] border border-gray-200 rounded-sm p-3 space-y-2">
        {items.length === 0 ? (
          <p className="text-xs text-gray-400">No selections yet.</p>
        ) : (
          items.map((item) => (
            <span
              key={item}
              className="inline-flex items-center gap-2 bg-gray-100 text-gray-700 text-xs font-semibold px-3 py-1 rounded-sm mr-2 mb-2"
            >
              {item}
              {onRemove && (
                <button
                  type="button"
                  onClick={() => onRemove(item)}
                  className="text-gray-500 hover:text-primary"
                  aria-label={`Remove ${item}`}
                >
                  ×
                </button>
              )}
            </span>
          ))
        )}
      </div>
    </div>
  );
}
