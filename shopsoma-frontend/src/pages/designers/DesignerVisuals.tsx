import { useState } from 'react';
import { ArrowRight } from 'lucide-react';
import { Link } from 'react-router-dom';
import type { Designer } from '../../services/designerService';
import { designerImage, designerPath } from './designerUtils';
import './designers.css';

export function DesignerCard({ designer }: { designer: Designer }) {
  const [failed, setFailed] = useState(false);
  return <Link className="designer-card" to={designerPath(designer.id)}>
    {!failed && <img src={designerImage(designer)} alt="" loading="lazy" onError={() => setFailed(true)} />}
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
      <p>{designer ? 'Explore the collection' : <>Discover independent designers<br />from across Africa and beyond.</>}</p>
    </div>
  </section>;
}
export function DesignerMessage({ title, children }: { title: string; children: React.ReactNode }) {
  return <div className="designer-message"><h2>{title}</h2>{children}</div>;
}
