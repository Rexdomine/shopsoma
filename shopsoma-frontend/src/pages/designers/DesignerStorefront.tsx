import { useEffect, useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { ChevronLeft } from 'lucide-react';
import Layout from '../../components/layout/Layout';
import { designerService, type Designer } from '../../services/designerService';
import ProductList from '../products/ProductList';
import { DesignerHero, DesignerMessage } from './DesignerVisuals';
import { readyDesigners } from './designerUtils';

export default function DesignerStorefront() {
  const { designerId } = useParams();
  const [state, setState] = useState<{ id?: string; designer?: Designer; error?: boolean; done?: boolean }>({});
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let current = true;
    setState({ id: designerId });
    // The public list is the eligibility authority: inactive, unapproved or
    // incomplete storefronts never resolve, even through a deep link.
    designerService.listDesigners().then(list => {
      if(current) setState({ id: designerId, done: true, designer: readyDesigners(list).find(d => d.id === designerId) });
    }).catch(() => { if(current) setState({ id: designerId, done: true, error: true }); });
    return () => { current = false; };
  }, [designerId,attempt]);
  const initialParams = useMemo(() => ({ vendor_id: designerId }), [designerId]);
  if(state.id !== designerId || !state.done) return <Layout><div role="status" aria-live="polite" className="designer-page"><div className="designer-hero designer-hero-loading" /><p className="sr-only">Loading designer</p></div></Layout>;
  if(state.error) return <Layout><div className="designer-page"><DesignerMessage eyebrow="Load error" title="We couldn’t load this designer"><p>Please check your connection and try again.</p><button type="button" onClick={() => setAttempt(n => n+1)}>Try again</button></DesignerMessage></div></Layout>;
  if(!state.designer) return <Layout><div className="designer-page"><DesignerMessage eyebrow="Designer unavailable" title="Designer unavailable"><p>This storefront is not available. Discover other designers on SHOPSOMA.</p><Link to="/designers">Browse designers</Link></DesignerMessage></div></Layout>;
  const designer = state.designer;
  return <ProductList key={designer.id} initialParams={initialParams} categoryNavAsTabs designerMode
    designerName={designer.business_name}
    storefrontHeader={<div className="designer-page">
      <DesignerHero key={designer.id} designer={designer}/>
      <div className="designer-intro max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        {/* Client direction (Nov 2026): storefronts match AMUJ — banner, name and catalogue only, no brand description. */}
        <Link to="/designers" className="designer-back-link"><ChevronLeft aria-hidden="true" size={14} />All designers</Link>
      </div>
    </div>}
    emptyCatalogState={<div className="designer-page"><DesignerMessage eyebrow="Published catalogue is empty" title="New pieces are on their way"><p>There are no published pieces available from {designer.business_name} right now.</p><Link to="/designers">Browse designers</Link></DesignerMessage></div>}
  />;
}
