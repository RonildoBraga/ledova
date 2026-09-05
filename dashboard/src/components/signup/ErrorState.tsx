import type { ErrorStateProps } from '@ledova/shared';

export default function ErrorState({
  title = 'Error Loading Data',
  message = 'We encountered an issue while loading required data.',
  retryLabel = 'Retry',
  onRetry,
  className = 'min-h-[calc(100vh-8rem)]',
}: ErrorStateProps) {
  return (
    <main
      className={`py-8 flex flex-col items-center justify-center bg-surface-base text-text-primary px-4 ${className}`}
    >
      <div className="w-full max-w-md text-center">
        <h2 className="text-lg font-light mb-4 text-error-light">{title}</h2>
        <p className="text-text-muted mb-4">{message}</p>
        <button
          onClick={onRetry}
          className="bg-surface-tertiary hover:bg-surface-disabled text-text-primary font-light py-2 px-4 rounded-md transition-colors"
        >
          {retryLabel}
        </button>
      </div>
    </main>
  );
}
