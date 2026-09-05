import type { ReactNode } from 'react';

interface PanelProps {
  title?: string | ReactNode;
  icon?: ReactNode;

  actions?: ReactNode;

  className?: string;

  children: ReactNode;
}

export function Panel({ title, icon, actions, className = '', children }: PanelProps) {
  return (
    <div className={`bg-surface-raised rounded-xl border border-border overflow-hidden flex flex-col ${className}`}>
      {title && (
        <div className="flex items-center justify-between py-4 px-4 bg-surface-raised flex-shrink-0">
          <div className="flex items-center gap-3 flex-1 min-w-0">
            {icon && <span className="text-text-muted flex-shrink-0">{icon}</span>}
            {typeof title === 'string' ? (
              <span className="text-lg font-semibold text-text-primary truncate">{title}</span>
            ) : (
              title
            )}
          </div>
          {actions && <div className="flex items-center flex-shrink-0">{actions}</div>}
        </div>
      )}

      <div className="px-4 pb-4 flex-1 min-h-0">{children}</div>
    </div>
  );
}
