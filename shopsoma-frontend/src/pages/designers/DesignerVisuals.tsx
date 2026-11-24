import { useState, type ReactNode } from 'react';
import { ArrowRight } from 'lucide-react';
import { Link } from 'react-router-dom';
import type { Designer } from '../../services/designerService';
import { designerImage, designerPath } from './designerUtils';
import './designers.css';

export function DesignerCard({ designer, featured = false }: { designer: Designer; featured?: boolean }) {
  const [failed, setFailed] = useState(false);
  return <Link className={`designer-card${featured ? ' designer-card-featured' : ''}${failed ? ' designer-card-fallback' : ''}`} to={designerPath(designer.id)} aria-label={`${designer.business_name} storefront`}>
    {!failed && <img src={designerImage(designer)} alt="" loading={featured ? 'eager' : 'lazy'} onError={() => setFailed(true)} />}
    <span className="designer-card-shade" />
    <span className="designer-card-caption"><span>{designer.business_name}</span><ArrowRight aria-hidden="true" /></span>
  </Link>;
}
export function DesignerHero({ designer }: { designer?: Designer }) {
  const [failed, setFailed] = useState(false);
  const image = designer ? designerImage(designer) : '/images/hero/shop-edits-2088.jpg';
  return <section className="designer-hero" aria-labelledby="designer-title">
    {!failed && <img src={image} alt="" fetchPriority="high" onError={() => setFailed(true)} />}
    <div className="designer-hero-shade" />
    <div className="designer-hero-content">
      <h1 id="designer-title">{designer ? designer.business_name : <>Shop by<br />Designer</>}</h1>
      {!designer && <p>Discover independent designers<br />from across Africa and beyond.</p>}
    </div>
  </section>;
}
export function DesignerMessage({ title, eyebrow, children }: { title: string; eyebrow?: string; children: ReactNode }) {
  return <div className="designer-message">{eyebrow && <p className="designer-message-eyebrow">{eyebrow}</p>}<h2>{title}</h2>{children}</div>;
}
