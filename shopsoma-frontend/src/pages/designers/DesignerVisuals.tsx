import { useState, type CSSProperties, type ReactNode } from 'react';
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
/**
 * Uncropped campaign photo for designer banners. The sharp photo fades at its
 * edge into a blurred copy of itself plus a blurred mirror reflection, so the
 * colours at the join match exactly and the photo reads as one continuous scene.
 * Shared by the storefront hero and the admin banner preview.
 */
export function DesignerBannerMedia({ src, alt = '', onError, priority = false }: {
  src: string; alt?: string; onError?: () => void; priority?: boolean;
}) {
  const [ratio, setRatio] = useState<number | null>(null);
  return <>
    <img className="designer-banner-backdrop designer-hero-backdrop" src={src} alt="" aria-hidden="true" />
    <div className="designer-banner-media" style={{ '--photo-ar': ratio ?? 1 } as CSSProperties}>
      <div className="designer-banner-reflection" aria-hidden="true">
        <img className="designer-banner-mirror designer-banner-mirror-left" src={src} alt="" />
        <img className="designer-banner-self" src={src} alt="" />
        <img className="designer-banner-mirror designer-banner-mirror-right" src={src} alt="" />
      </div>
      <img
        className="designer-banner-photo designer-hero-photo"
        src={src}
        alt={alt}
        fetchPriority={priority ? 'high' : undefined}
        onLoad={(event) => {
          const { naturalWidth, naturalHeight } = event.currentTarget;
          if (naturalWidth && naturalHeight) setRatio(naturalWidth / naturalHeight);
        }}
        onError={onError}
      />
    </div>
  </>;
}
export function DesignerHero({ designer }: { designer?: Designer }) {
  const [failed, setFailed] = useState(false);
  const image = designer ? designerImage(designer) : '/images/hero/shop-edits-2088.jpg';
  // Designer campaign images come in any shape, so storefront heroes never crop
  // (see DesignerBannerMedia). The curated directory banner keeps its full-bleed crop.
  return <section className={`designer-hero${designer ? ' designer-hero-storefront designer-banner' : ''}`} aria-labelledby="designer-title">
    {!failed && designer && <DesignerBannerMedia src={image} priority onError={() => setFailed(true)} />}
    {!failed && !designer && <img src={image} alt="" fetchPriority="high" onError={() => setFailed(true)} />}
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
