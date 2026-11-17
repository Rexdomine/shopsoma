import { useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Search, X } from 'lucide-react';
import Layout from '../../components/layout/Layout';
import { designerService, type Designer } from '../../services/designerService';
import { DesignerCard, DesignerHero, DesignerMessage } from './DesignerVisuals';
import { readyDesigners, filterDesigners, featuredDesigners } from './designerUtils';

const letters = ['All', ...'ABCDEFGHIJKLMNOPQRSTUVWXYZ', '#'];
export default function Designers() {
  const [params, setParams] = useSearchParams();
  const query = params.get('q') || '';
  const requestedLetter = params.get('letter') || 'All';
  const letter = letters.includes(requestedLetter) ? requestedLetter : 'All';
  const [designers, setDesigners] = useState<Designer[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let current = true;
    setLoading(true); setError(false); setDesigners([]);
    designerService.listDesigners().then(data => { if(current) setDesigners(readyDesigners(data)); })
      .catch(() => { if(current) setError(true); })
      .finally(() => { if(current) setLoading(false); });
    return () => { current = false; };
  }, [attempt]);
  const featured = useMemo(() => featuredDesigners(designers), [designers]);
  const results = useMemo(() => filterDesigners(designers, query, letter), [designers,query,letter]);
  const search = (value: string) => setParams(previous => {
    const next = new URLSearchParams(previous); next.delete('letter');
    if(value) next.set('q',value); else next.delete('q'); return next;
  }, { replace: true });
  const chooseLetter = (value: string) => setParams(previous => {
    const next = new URLSearchParams(previous); next.delete('q');
    if(value !== 'All') next.set('letter',value); else next.delete('letter'); return next;
  });
  return <Layout><div className="designer-page">
    <DesignerHero />
    <div className="designer-container">
      {loading ? <div role="status" className="designer-loading">Loading designers…<div className="designer-grid">{[1,2,3,4].map(n => <div className="designer-skeleton" key={n} />)}</div></div> : error ?
        <DesignerMessage title="We couldn’t load designers"><p>Please try again. Your search has been kept.</p><button onClick={() => setAttempt(n => n+1)}>Try again</button></DesignerMessage> : <>
        {featured.length > 0 && <section aria-labelledby="featured-heading" className="designer-featured"><h2 id="featured-heading" className="designer-eyebrow">Featured Designers</h2><div className="designer-grid">{featured.map(d => <DesignerCard key={d.id} designer={d} />)}</div></section>}
        <section className="designer-directory" aria-labelledby="directory-heading">
          <div className="designer-directory-bar"><h2 id="directory-heading" className="designer-eyebrow">Designers A–Z</h2>
            <form className="designer-search" role="search" onSubmit={e => e.preventDefault()}><label className="sr-only" htmlFor="designer-search">Search designers by name</label><Search aria-hidden="true" size={20}/><input id="designer-search" type="search" value={query} placeholder="Search designers by name" onChange={e => search(e.target.value)} />{query && <button type="button" aria-label="Clear designer search" onClick={() => search('')}><X size={18}/></button>}</form>
          </div>
          <nav className="designer-alphabet" aria-label="Browse designers alphabetically">{letters.map(l => <button key={l} aria-pressed={!query && letter === l} onClick={() => chooseLetter(l)}>{l}</button>)}</nav>
          <div className="designer-results-heading"><h3>{query ? `Results for “${query.trim()}”` : letter === 'All' ? 'All designers' : `Designers: ${letter}`}</h3><span role="status">{results.length} {results.length === 1 ? 'designer' : 'designers'}</span></div>
          {results.length ? <div className="designer-grid">{results.map(d => <DesignerCard key={d.id} designer={d}/>)}</div> : <DesignerMessage title={designers.length ? 'No designers found' : 'Designers are coming soon'}><p>{designers.length ? 'Try another name or browse all designers.' : 'Please check back soon.'}</p>{designers.length > 0 && <button onClick={() => chooseLetter('All')}>Browse all designers</button>}</DesignerMessage>}
        </section>
      </>}
    </div>
  </div></Layout>;
}
