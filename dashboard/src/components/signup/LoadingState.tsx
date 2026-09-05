import type { LoadingStateProps } from '@ledova/shared';

export default function LoadingState({
  message = 'Loading data...',
  className = 'min-h-[calc(100vh-8rem)]',
}: LoadingStateProps) {
  return (
    <main
      className={`py-8 flex flex-col items-center justify-center bg-surface-base text-text-primary px-4 ${className}`}
    >
      <div className="text-center">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-text-body mx-auto"></div>
        <p className="mt-4 text-text-muted">{message}</p>
      </div>
    </main>
  );
}
