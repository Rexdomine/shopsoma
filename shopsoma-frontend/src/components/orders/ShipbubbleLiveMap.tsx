import { useEffect, useRef, useState } from 'react';
import type { ShipbubbleTrackingData } from '../../services/orderService';

declare global {
  interface Window {
    L?: any;
  }
}

interface ShipbubbleLiveMapProps {
  data: ShipbubbleTrackingData;
  currentStatus?: string;
  isSyncing?: boolean;
  isSimulating?: boolean;
  onSync?: () => void;
  onSimulate?: (statusKey: string) => void;
  fullBleed?: boolean;
}

const LEAFLET_CSS_ID = 'leaflet-cdn-css';
const LEAFLET_JS_ID = 'leaflet-cdn-js';

type MapTileStyle = 'street' | 'osm' | 'warm' | 'satellite';

const FREE_TILE_LAYERS: Record<
  MapTileStyle,
  { label: string; url: string; attribution: string; maxZoom: number }
> = {
  street: {
    label: 'Street',
    url: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}',
    attribution: 'Tiles &copy; Esri &mdash; OpenStreetMap contributors',
    maxZoom: 19,
  },
  osm: {
    label: 'Standard',
    url: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    maxZoom: 19,
  },
  warm: {
    label: 'Warm',
    url: 'https://{s}.tile.openstreetmap.fr/hot/{z}/{x}/{y}.png',
    attribution: '&copy; OpenStreetMap contributors, Tiles style by Humanitarian OSM Team',
    maxZoom: 19,
  },
  satellite: {
    label: 'Satellite',
    url: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
    attribution: 'Tiles &copy; Esri &mdash; Source: Esri, Maxar, Earthstar Geographics',
    maxZoom: 18,
  },
};

function ensureLeafletLoaded(): Promise<any> {
  return new Promise((resolve, reject) => {
    if (typeof window === 'undefined') {
      reject(new Error('Window unavailable'));
      return;
    }
    if (window.L) {
      resolve(window.L);
      return;
    }

    if (!document.getElementById(LEAFLET_CSS_ID)) {
      const link = document.createElement('link');
      link.id = LEAFLET_CSS_ID;
      link.rel = 'stylesheet';
      link.href = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.css';
      link.crossOrigin = '';
      document.head.appendChild(link);
    }

    const existingScript = document.getElementById(LEAFLET_JS_ID) as HTMLScriptElement | null;
    if (existingScript) {
      existingScript.addEventListener('load', () => resolve(window.L));
      existingScript.addEventListener('error', () => reject(new Error('Failed to load Leaflet')));
      return;
    }

    const script = document.createElement('script');
    script.id = LEAFLET_JS_ID;
    script.src = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.js';
    script.crossOrigin = '';
    script.async = true;
    script.onload = () => resolve(window.L);
    script.onerror = () => reject(new Error('Failed to load Leaflet script'));
    document.body.appendChild(script);
  });
}

export default function ShipbubbleLiveMap({
  data,
  fullBleed = false,
}: ShipbubbleLiveMapProps) {
  const mapContainerRef = useRef<HTMLDivElement | null>(null);
  const mapInstanceRef = useRef<any>(null);
  const tileLayerRef = useRef<any>(null);
  const layersRef = useRef<{
    completedLine?: any;
    remainingLine?: any;
    glowLine?: any;
    originMarker?: any;
    destMarker?: any;
    courierMarker?: any;
  }>({});
  const [mapReady, setMapReady] = useState(false);
  const [mapError, setMapError] = useState<string | null>(null);
  const [tileStyle, setTileStyle] = useState<MapTileStyle>('street');

  useEffect(() => {
    let cancelled = false;
    ensureLeafletLoaded()
      .then((L) => {
        if (cancelled || !mapContainerRef.current) return;
        if (!mapInstanceRef.current) {
          const map = L.map(mapContainerRef.current, {
            center: [data.current_location.lat, data.current_location.lng],
            zoom: 7,
            zoomControl: false,
            scrollWheelZoom: true,
          });

          L.control.zoom({ position: 'bottomright' }).addTo(map);

          const initialTile = FREE_TILE_LAYERS[tileStyle];
          tileLayerRef.current = L.tileLayer(initialTile.url, {
            attribution: initialTile.attribution,
            maxZoom: initialTile.maxZoom,
          }).addTo(map);

          mapInstanceRef.current = map;
        }
        setMapReady(true);
      })
      .catch(() => {
        if (!cancelled) {
          setMapError('Unable to load interactive map tiles.');
        }
      });

    return () => {
      cancelled = true;
    };
  }, []);

  // Switch tile layer cleanly when user selects a different style
  useEffect(() => {
    if (!mapReady || !mapInstanceRef.current || !window.L) return;
    const L = window.L;
    const map = mapInstanceRef.current;
    const chosen = FREE_TILE_LAYERS[tileStyle];
    if (tileLayerRef.current) {
      map.removeLayer(tileLayerRef.current);
    }
    tileLayerRef.current = L.tileLayer(chosen.url, {
      attribution: chosen.attribution,
      maxZoom: chosen.maxZoom,
    }).addTo(map);
  }, [tileStyle, mapReady]);

  // Render markers and route polylines whenever tracking data updates
  useEffect(() => {
    if (!mapReady || !mapInstanceRef.current || !window.L) return;
    const L = window.L;
    const map = mapInstanceRef.current;
    const layers = layersRef.current;

    Object.values(layers).forEach((layer) => {
      if (layer && map.hasLayer(layer)) {
        map.removeLayer(layer);
      }
    });

    const waypoints =
      data.route_waypoints && data.route_waypoints.length >= 2
        ? data.route_waypoints
        : [
            [data.origin.lat, data.origin.lng],
            [data.destination.lat, data.destination.lng],
          ];

    const progress = Math.max(0, Math.min(1, data.current_location.progress ?? 0.1));
    const splitIdx = Math.max(
      1,
      Math.min(waypoints.length - 1, Math.round(progress * (waypoints.length - 1)))
    );

    const completedPoints = waypoints.slice(0, splitIdx + 1);
    completedPoints[completedPoints.length - 1] = [
      data.current_location.lat,
      data.current_location.lng,
    ];
    const remainingPoints = [
      [data.current_location.lat, data.current_location.lng],
      ...waypoints.slice(splitIdx),
    ];

    // Subtle outer glow on completed segment
    layers.glowLine = L.polyline(completedPoints, {
      color: '#10b981',
      weight: 10,
      opacity: 0.22,
      lineCap: 'round',
    }).addTo(map);

    // Completed segment (emerald/dark solid line)
    layers.completedLine = L.polyline(completedPoints, {
      color: '#059669',
      weight: 4.5,
      opacity: 0.95,
      lineCap: 'round',
    }).addTo(map);

    // Remaining segment (dashed slate/indigo line)
    layers.remainingLine = L.polyline(remainingPoints, {
      color: '#475569',
      weight: 3.5,
      opacity: 0.75,
      dashArray: '8, 8',
      lineCap: 'round',
    }).addTo(map);

    // Origin Hub Custom Icon
    const originIcon = L.divIcon({
      className: 'shopsoma-map-pin-origin',
      html: `
        <div style="position:relative;display:flex;align-items:center;justify-content:center;width:36px;height:36px;">
          <div style="position:absolute;width:36px;height:36px;border-radius:9999px;background:rgba(17,24,39,0.18);"></div>
          <div style="width:28px;height:28px;border-radius:9999px;background:#111827;border:2.5px solid #ffffff;box-shadow:0 4px 12px rgba(0,0,0,0.3);display:flex;align-items:center;justify-content:center;color:#ffffff;font-size:11px;font-weight:800;">
            H
          </div>
        </div>
      `,
      iconSize: [36, 36],
      iconAnchor: [18, 18],
    });

    // Destination Custom Icon
    const destIcon = L.divIcon({
      className: 'shopsoma-map-pin-dest',
      html: `
        <div style="position:relative;display:flex;align-items:center;justify-content:center;width:36px;height:36px;">
          <div style="position:absolute;width:36px;height:36px;border-radius:9999px;background:rgba(180,83,9,0.2);"></div>
          <div style="width:28px;height:28px;border-radius:9999px;background:#b45309;border:2.5px solid #ffffff;box-shadow:0 4px 12px rgba(0,0,0,0.3);display:flex;align-items:center;justify-content:center;color:#ffffff;font-size:13px;font-weight:700;">
            ★
          </div>
        </div>
      `,
      iconSize: [36, 36],
      iconAnchor: [18, 18],
    });

    // Live Courier Animated Pulse Icon
    const courierIcon = L.divIcon({
      className: 'shopsoma-map-pin-courier',
      html: `
        <div style="position:relative;display:flex;align-items:center;justify-content:center;width:54px;height:54px;">
          <span style="position:absolute;width:52px;height:52px;border-radius:9999px;background:rgba(5,150,105,0.28);animation:ping 1.8s cubic-bezier(0,0,0.2,1) infinite;"></span>
          <div style="position:relative;width:38px;height:38px;border-radius:9999px;background:#059669;border:3px solid #ffffff;box-shadow:0 6px 16px rgba(5,150,105,0.45);display:flex;align-items:center;justify-content:center;color:#ffffff;font-size:17px;">
            🚚
          </div>
        </div>
      `,
      iconSize: [54, 54],
      iconAnchor: [27, 27],
    });

    layers.originMarker = L.marker([data.origin.lat, data.origin.lng], {
      icon: originIcon,
    })
      .addTo(map)
      .bindPopup(
        `<div style="font-family:sans-serif;min-width:190px;padding:2px;">
          <p style="margin:0;font-size:10px;text-transform:uppercase;letter-spacing:0.1em;color:#6b7280;font-weight:700;">Origin Fulfillment Hub</p>
          <p style="margin:4px 0 2px;font-size:13px;font-weight:700;color:#111827;">${data.origin.name}</p>
          <p style="margin:0;font-size:11px;color:#4b5563;">${data.origin.address}</p>
        </div>`
      );

    layers.destMarker = L.marker([data.destination.lat, data.destination.lng], {
      icon: destIcon,
    })
      .addTo(map)
      .bindPopup(
        `<div style="font-family:sans-serif;min-width:190px;padding:2px;">
          <p style="margin:0;font-size:10px;text-transform:uppercase;letter-spacing:0.1em;color:#b45309;font-weight:700;">Delivery Destination</p>
          <p style="margin:4px 0 2px;font-size:13px;font-weight:700;color:#111827;">${data.destination.name}</p>
          <p style="margin:0;font-size:11px;color:#4b5563;">${data.destination.address}</p>
        </div>`
      );

    layers.courierMarker = L.marker(
      [data.current_location.lat, data.current_location.lng],
      { icon: courierIcon, zIndexOffset: 1000 }
    )
      .addTo(map)
      .bindPopup(
        `<div style="font-family:sans-serif;min-width:210px;padding:2px;">
          <p style="margin:0;font-size:10px;text-transform:uppercase;letter-spacing:0.1em;color:#059669;font-weight:700;">${data.courier_name} • Live GPS</p>
          <p style="margin:4px 0 3px;font-size:12.5px;font-weight:700;color:#111827;">${data.current_location.status_label}</p>
          <p style="margin:0;font-size:11px;color:#6b7280;">Route Completion: <strong>${Math.round(progress * 100)}%</strong> • ETA: ${data.delivery_eta}</p>
        </div>`
      );

    const bounds = L.latLngBounds(waypoints);
    map.fitBounds(bounds, { padding: [65, 65], maxZoom: 12 });
    setTimeout(() => {
      map.invalidateSize();
    }, 150);
  }, [mapReady, data]);

  const handleRecenterRoute = () => {
    if (!mapInstanceRef.current || !window.L) return;
    const L = window.L;
    const waypoints =
      data.route_waypoints && data.route_waypoints.length >= 2
        ? data.route_waypoints
        : [
            [data.origin.lat, data.origin.lng],
            [data.destination.lat, data.destination.lng],
          ];
    mapInstanceRef.current.fitBounds(L.latLngBounds(waypoints), {
      padding: [65, 65],
      maxZoom: 12,
    });
  };

  const handleFocusCourier = () => {
    if (!mapInstanceRef.current) return;
    mapInstanceRef.current.flyTo(
      [data.current_location.lat, data.current_location.lng],
      10,
      { duration: 0.9 }
    );
    if (layersRef.current.courierMarker) {
      layersRef.current.courierMarker.openPopup();
    }
  };

  const progressPct = Math.round((data.current_location.progress ?? 0.06) * 100);

  return (
    <div
      className={
        fullBleed
          ? 'relative w-full h-full min-h-[540px] bg-slate-100 overflow-hidden'
          : 'relative w-full h-[520px] rounded-xl border border-gray-200 bg-slate-100 overflow-hidden shadow-sm'
      }
    >
      {/* Top-Left Floating Status Card */}
      <div className="absolute top-4 left-4 z-[400] max-w-[calc(100%-2rem)] sm:max-w-md pointer-events-auto">
        <div className="bg-white/95 backdrop-blur-sm border border-gray-200 rounded-sm px-4 py-3 shadow-sm flex items-center gap-3">
          {data.courier_image ? (
            <img
              src={data.courier_image}
              alt={data.courier_name}
              className="w-9 h-9 rounded-full object-cover border border-gray-200 bg-white shrink-0"
            />
          ) : (
            <div className="w-9 h-9 rounded-full bg-primary/10 text-primary flex items-center justify-center text-xs font-semibold shrink-0">
              SB
            </div>
          )}
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-xs font-semibold text-gray-900 truncate">
                {data.courier_name}
              </span>
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-primary/10 text-primary">
                {progressPct}% Route
              </span>
              {data.shipbubble_order_id && (
                <span className="text-[10px] font-mono text-gray-500 bg-gray-100 px-1.5 py-0.5 rounded-sm">
                  {data.shipbubble_order_id}
                </span>
              )}
            </div>
            <p className="text-xs text-gray-600 mt-0.5 truncate">
              {data.current_location.status_label}
            </p>
          </div>
        </div>
      </div>

      {/* Top-Right Floating Map Layer Switcher & Camera Controls */}
      <div className="absolute top-4 right-4 z-[400] flex flex-col sm:flex-row items-end sm:items-center gap-2 pointer-events-auto">
        <div className="bg-white/95 backdrop-blur-sm border border-gray-200 rounded-sm p-1 shadow-sm flex items-center gap-1">
          {(Object.keys(FREE_TILE_LAYERS) as MapTileStyle[]).map((styleKey) => {
            const active = tileStyle === styleKey;
            return (
              <button
                key={styleKey}
                type="button"
                onClick={() => setTileStyle(styleKey)}
                className={`px-2.5 py-1 rounded-sm text-[11px] font-semibold transition ${
                  active
                    ? 'bg-primary text-white'
                    : 'text-gray-600 hover:text-gray-900 hover:bg-gray-100'
                }`}
              >
                {FREE_TILE_LAYERS[styleKey].label}
              </button>
            );
          })}
        </div>

        <div className="flex items-center gap-1.5">
          <button
            type="button"
            onClick={handleFocusCourier}
            className="px-3 py-1.5 bg-primary hover:bg-primary-dark text-white text-[11px] font-semibold rounded-sm shadow-sm transition"
          >
            Focus Courier
          </button>
          <button
            type="button"
            onClick={handleRecenterRoute}
            className="px-3 py-1.5 bg-white/95 hover:bg-gray-50 text-gray-700 border border-gray-200 text-[11px] font-semibold rounded-sm shadow-sm transition"
          >
            Fit Route
          </button>
        </div>
      </div>

      {/* Main Leaflet Canvas */}
      {mapError ? (
        <div className="h-full w-full flex items-center justify-center p-6 text-xs text-gray-500">
          {mapError}
        </div>
      ) : (
        <div
          ref={mapContainerRef}
          className="w-full h-full min-h-[540px] z-0"
          aria-label="ShipBubble Live Delivery Route Map"
        />
      )}

      {/* Bottom-Left Floating Route & Coordinate Bar (Clean White) */}
      <div className="absolute bottom-4 left-4 z-[400] hidden sm:flex items-center gap-3 bg-white/95 backdrop-blur-sm text-gray-700 px-4 py-2 rounded-sm shadow-sm border border-gray-200 pointer-events-auto">
        <div className="flex items-center gap-2 pr-3 border-r border-gray-200">
          <span className="w-2 h-2 rounded-full bg-primary" />
          <span className="text-[10px] font-semibold tracking-[0.15em] uppercase text-gray-500">
            Live Coordinates
          </span>
        </div>
        <div className="text-[11px] font-mono text-gray-700">
          {data.current_location.lat.toFixed(4)}° N, {data.current_location.lng.toFixed(4)}° E
        </div>
        <div className="text-[11px] text-gray-500 pl-3 border-l border-gray-200">
          {data.origin.city} → {data.destination.city}
        </div>
      </div>
    </div>
  );
}
