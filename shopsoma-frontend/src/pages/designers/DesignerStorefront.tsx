import { useEffect, useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
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
    designerService.listDesigners().then(list => {
      if(current) setState({ id: designerId, done: true, designer: readyDesigners(list).find(d => d.id === designerId) });
    }).catch(() => { if(current) setState({ id: designerId, done: true, error: true }); });
    return () => { current = false; };
  }, [designerId,attempt]);
  const initialParams = useMemo(() => ({ vendor_id: designerId }), [designerId]);
  if(state.id !== designerId || !state.done) return <Layout><div role="status" className="designer-message">Loading designer…</div></Layout>;
  if(state.error) return <Layout><DesignerMessage title="We couldn’t load this designer"><button onClick={() => setAttempt(n => n+1)}>Try again</button></DesignerMessage></Layout>;
  if(!state.designer) return <Layout><DesignerMessage title="Designer unavailable"><p>This storefront is not available.</p><Link to="/designers">Browse designers</Link></DesignerMessage></Layout>;
  const designer = state.designer;
  return <ProductList key={designer.id} initialParams={initialParams} categoryNavAsTabs designerMode
    storefrontHeader={<><DesignerHero key={designer.id} designer={designer}/><div className="designer-container designer-intro"><Link to="/designers">← All designers</Link>{designer.business_description && <p>{designer.business_description}</p>}</div></>}
  />;
}
