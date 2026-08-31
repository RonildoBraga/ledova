import type { CSSProperties } from 'react';

interface QRScannerViewProps {
  scannerId: string;
  error?: string | null;
  className?: string;
  style?: CSSProperties;
}

export function QRScannerView({ scannerId, error, className, style }: QRScannerViewProps) {
  return (
    <div className={className ?? 'relative overflow-hidden rounded-lg bg-black'} style={style}>
      <div id={scannerId} className="w-full aspect-square" />
      {error && <p className="text-error-light text-xs mt-2">{error}</p>}
    </div>
  );
}
