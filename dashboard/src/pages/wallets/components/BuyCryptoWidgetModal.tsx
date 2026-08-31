import { useEffect } from 'react';
import { Modal } from '@components/Modal';

interface BuyCryptoWidgetModalProps {
  isOpen: boolean;
  onClose: () => void;
  onComplete?: () => void;
  widgetUrl: string | null;
}

export function BuyCryptoWidgetModal({ isOpen, onClose, onComplete, widgetUrl }: BuyCryptoWidgetModalProps) {
  useEffect(() => {
    if (!isOpen) return;

    const handleMessage = (event: MessageEvent) => {
      // Transak sends events via postMessage from the iframe
      if (event.origin !== 'https://global.transak.com') return;

      const data = typeof event.data === 'string' ? JSON.parse(event.data) : event.data;
      const eventId = data?.event_id;

      if (eventId === 'TRANSAK_ORDER_SUCCESSFUL') {
        onComplete?.();
        onClose();
      } else if (eventId === 'TRANSAK_WIDGET_CLOSE') {
        onClose();
      }
    };

    window.addEventListener('message', handleMessage);
    return () => window.removeEventListener('message', handleMessage);
  }, [isOpen, onClose, onComplete]);

  return (
    <Modal isOpen={isOpen} onClose={onClose} size="lg" fullHeight>
      <div className="h-[650px] rounded-lg overflow-hidden">
        {widgetUrl ? (
          <iframe
            src={widgetUrl}
            className="w-full h-full border-0"
            title="Buy Digital Assets"
            allow="camera;microphone;payment"
            referrerPolicy="strict-origin-when-cross-origin"
          />
        ) : (
          <div className="flex flex-col items-center justify-center h-full gap-3">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-brand-mid" />
            <span className="text-sm text-text-muted">Loading...</span>
          </div>
        )}
      </div>
    </Modal>
  );
}
