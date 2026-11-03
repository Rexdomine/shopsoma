import { useEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { Search, X } from 'lucide-react';
import Layout from '../../components/layout/Layout';
import Loading from '../../components/common/Loading';
import {
  DESIGNERS_HERO_IMAGE_URL,
  DESIGNERS_HERO_MOBILE_IMAGE_URL,
  getDesignerStorefrontPath,
} from '../../config/constants';
import {
  DEFAULT_DESIGNER_IMAGE_FALLBACK,
  designerService,
  getDesignerDirectoryImageUrl,
  type Designer,
} from '../../services/designerService';

const ALPHABET = Array.from({ length: 26 }, (_, index) =>
  String.fromCharCode(65 + index),
);

const getDesignerStartingLetter = (name: string): string => {
  const trimmed = (name || '').trim();
  if (!trimmed) return '#';
  const firstChar = trimmed.charAt(0).toUpperCase();
  return /^[A-Z]$/.test(firstChar) ? firstChar : '#';
};

export default function Designers() {
  const [designers, setDesigners] = useState<Designer[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedLetter, setSelectedLetter] = useState<string>('All');
  const [searchQuery, setSearchQuery] = useState<string>('');
  const directoryRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    let isCurrent = true;
    const loadDesigners = async () => {
      try {
        setLoading(true);
        const data = await designerService.listDesigners();
        if (!isCurrent) return;
        const sorted = [...(Array.isArray(data) ? data : [])].sort((a, b) =>
          (a.business_name || '').localeCompare(b.business_name || '', undefined, {
            sensitivity: 'base',
          }),
        );
        setDesigners(sorted);
        setError(null);
      } catch (err) {
        if (!isCurrent) return;
        console.error('Failed to load designers', err);
        setDesigners([]);
        setError('Unable to load designers right now.');
      } finally {
        if (isCurrent) {
          setLoading(false);
        }
      }
    };

    loadDesigners();
    return () => {
      isCurrent = false;
    };
  }, []);

  const availableLetters = useMemo(() => {
    const letters = new Set<string>();
    designers.forEach((designer) => {
      letters.add(getDesignerStartingLetter(designer.business_name));
    });
    return letters;
  }, [designers]);

  const filteredDesigners = useMemo(() => {
    const normalizedSearch = searchQuery.trim().toLowerCase();
    return designers.filter((designer) => {
      const name = (designer.business_name || '').trim();
      if (selectedLetter !== 'All') {
        if (getDesignerStartingLetter(name) !== selectedLetter) {
          return false;
        }
      }
      if (normalizedSearch) {
        return name.toLowerCase().includes(normalizedSearch);
      }
      return true;
    });
  }, [designers, selectedLetter, searchQuery]);

  const handleLetterSelect = (letter: string) => {
    setSelectedLetter((prev) => (prev === letter && letter !== 'All' ? 'All' : letter));
  };

  const handleClearFilters = () => {
    setSelectedLetter('All');
    setSearchQuery('');
  };

  const scrollToDirectory = () => {
    if (directoryRef.current && typeof directoryRef.current.scrollIntoView === 'function') {
      directoryRef.current.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  };

  if (loading) {
    return <Loading fullScreen message="Loading designers..." />;
  }

  return (
    <Layout>
      {/* Storefront Photoshoot Hero Banner (Shop Edits pattern) */}
      <section className="relative w-full min-h-[50vh] overflow-hidden flex items-end">
        <picture className="absolute inset-0" aria-hidden="true">
          <source media="(max-width: 639px)" srcSet={DESIGNERS_HERO_MOBILE_IMAGE_URL} />
          <img
            src={DESIGNERS_HERO_IMAGE_URL}
            alt=""
            onError={(event) => {
              if (!event.currentTarget.src.endsWith(DEFAULT_DESIGNER_IMAGE_FALLBACK)) {
                event.currentTarget.src = DEFAULT_DESIGNER_IMAGE_FALLBACK;
              }
            }}
            className="h-full w-full object-cover object-center sm:object-top"
          />
        </picture>
        <div className="absolute inset-0 bg-black/20" />

        <div className="relative z-10 max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 w-full pb-8 sm:pb-12 lg:pb-16">
          <div className="max-w-md">
            <h1
              className="text-2xl sm:text-3xl lg:text-4xl font-display text-white mb-3 sm:mb-4 break-words"
              style={{ textShadow: '0 2px 8px rgba(0,0,0,0.4)' }}
            >
              Shop by Designer
            </h1>
            <p
              className="text-xs sm:text-sm font-serif text-white/95 leading-relaxed mb-4 sm:mb-6 break-words"
              style={{ textShadow: '0 1px 4px rgba(0,0,0,0.3)' }}
            >
              Discover independent luxury houses, contemporary ateliers, and heritage artisans shaping modern African fashion.
            </p>
            <button
              type="button"
              onClick={scrollToDirectory}
              className="inline-block px-5 sm:px-6 py-2 sm:py-2.5 bg-white/10 backdrop-blur-sm border border-white text-white text-[11px] sm:text-xs font-ui uppercase tracking-[0.2em] hover:bg-white hover:text-dark transition-all max-w-full truncate"
            >
              Explore Designers
            </button>
          </div>
        </div>
      </section>

      {/* Directory Controls Bar (Category-area position from Shop Edits) */}
      <section
        ref={directoryRef}
        id="designer-directory"
        className="bg-[var(--color-page-bg)] border-b border-gray-200 w-full"
      >
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4 sm:py-6 space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div className="flex items-center gap-3 sm:gap-6">
              <button
                type="button"
                onClick={() => setSelectedLetter('All')}
                className={`text-xs sm:text-sm font-ui tracking-wide pb-1 border-b-2 whitespace-nowrap transition ${
                  selectedLetter === 'All'
                    ? 'text-dark border-primary'
                    : 'text-gray-500 border-transparent hover:text-dark hover:border-gray-300'
                }`}
              >
                All Designers ({filteredDesigners.length})
              </button>
            </div>

            {/* Designer Name Search */}
            <div className="relative w-full sm:w-72 md:w-80">
              <Search className="w-4 h-4 text-gray-400 absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" />
              <input
                type="search"
                value={searchQuery}
                onChange={(event) => setSearchQuery(event.target.value)}
                placeholder="Search designers by name..."
                aria-label="Search designers by name"
                className="w-full pl-9 pr-8 py-2 text-xs sm:text-sm font-ui bg-white/80 border border-gray-300 text-dark placeholder:text-gray-400 focus:outline-none focus:border-primary transition-colors"
              />
              {searchQuery && (
                <button
                  type="button"
                  onClick={() => setSearchQuery('')}
                  aria-label="Clear designer search"
                  className="absolute right-2.5 top-1/2 -translate-y-1/2 text-gray-400 hover:text-dark"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              )}
            </div>
          </div>

          {/* A-Z Alphabetical Browsing Bar */}
          <div
            role="navigation"
            aria-label="Alphabetical designer filter"
            className="flex items-center gap-1 sm:gap-1.5 overflow-x-auto pb-1 no-scrollbar"
          >
            <button
              type="button"
              onClick={() => handleLetterSelect('All')}
              aria-pressed={selectedLetter === 'All'}
              className={`px-2.5 py-1 text-xs font-ui uppercase tracking-wider border transition shrink-0 ${
                selectedLetter === 'All'
                  ? 'border-primary bg-primary text-white font-semibold'
                  : 'border-transparent text-gray-600 hover:text-primary hover:border-primary/30'
              }`}
            >
              All
            </button>
            {ALPHABET.map((letter) => {
              const isSelected = selectedLetter === letter;
              const hasDesigners = availableLetters.has(letter);
              return (
                <button
                  key={letter}
                  type="button"
                  onClick={() => handleLetterSelect(letter)}
                  aria-pressed={isSelected}
                  aria-label={`Filter by letter ${letter}`}
                  className={`w-7 h-7 sm:w-8 sm:h-8 flex items-center justify-center text-xs font-ui uppercase border transition shrink-0 ${
                    isSelected
                      ? 'border-primary bg-primary text-white font-semibold'
                      : hasDesigners
                        ? 'border-transparent text-dark hover:text-primary hover:border-primary/40 font-medium'
                        : 'border-transparent text-gray-400 hover:text-gray-600'
                  }`}
                >
                  {letter}
                </button>
              );
            })}
          </div>
        </div>
      </section>

      {/* Designer Directory Grid */}
      <section className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 sm:py-12">
        {error && (
          <div
            role="alert"
            className="border border-red-200 bg-red-50 text-red-700 rounded-sm p-4 text-sm font-ui"
          >
            {error}
          </div>
        )}

        {!error && designers.length === 0 && (
          <div className="border border-gray-200 bg-white/60 p-10 text-center text-gray-600 font-ui text-sm">
            No approved designers are available yet. Please check back soon.
          </div>
        )}

        {!error && designers.length > 0 && filteredDesigners.length === 0 && (
          <div className="border border-gray-200 bg-white/60 p-10 text-center space-y-4">
            <p className="text-sm font-ui text-gray-600">
              No designers match your current search or alphabetical filter.
            </p>
            <button
              type="button"
              onClick={handleClearFilters}
              className="px-5 py-2 border border-primary text-primary text-xs font-ui uppercase tracking-[0.2em] hover:bg-primary hover:text-white transition"
            >
              Reset Filters
            </button>
          </div>
        )}

        {!error && filteredDesigners.length > 0 && (
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-6 sm:gap-8">
            {filteredDesigners.map((designer) => {
              const imageUrl = getDesignerDirectoryImageUrl(designer);
              return (
                <Link
                  key={designer.id}
                  to={getDesignerStorefrontPath(designer.id)}
                  data-testid={`designer-card-${designer.id}`}
                  className="group block"
                >
                  <div className="relative overflow-hidden aspect-[3/4] bg-[#EBE6DC] mb-3 border border-primary/10">
                    <img
                      src={imageUrl}
                      alt={designer.business_name}
                      loading="lazy"
                      onError={(event) => {
                        if (!event.currentTarget.src.endsWith(DEFAULT_DESIGNER_IMAGE_FALLBACK)) {
                          event.currentTarget.src = DEFAULT_DESIGNER_IMAGE_FALLBACK;
                        }
                      }}
                      className="w-full h-full object-cover object-center transition-transform duration-500 group-hover:scale-105"
                    />
                    <div className="absolute inset-0 bg-black/10 group-hover:bg-black/20 transition-colors duration-300" />
                  </div>

                  <div className="space-y-1">
                    <p className="text-[10px] font-ui uppercase tracking-[0.25em] text-primary/70">
                      Designer
                    </p>
                    <h2 className="text-base sm:text-lg font-serif text-dark group-hover:text-primary transition-colors leading-snug">
                      {designer.business_name}
                    </h2>
                  </div>
                </Link>
              );
            })}
          </div>
        )}
      </section>
    </Layout>
  );
}
