import { usePageTitle } from '@hooks/usePageTitle';
import { useHeaderActions } from '@hooks/useHeaderActions';
import { ThemeToggle } from '@components/ThemeToggle';
import { NotificationBell } from '@components/NotificationBell';

export function DesktopHeader() {
  const { title, subtitle } = usePageTitle();
  const { actions } = useHeaderActions();

  return (
    <header className="h-16 flex items-center justify-between px-6 border-b border-border-subtle/30 bg-surface-base/50 backdrop-blur-sm">
      <div className="min-w-0 flex-1">
        <h1 className="text-lg font-medium text-text-primary">{title}</h1>
        {subtitle && <p className="text-xs text-text-muted truncate">{subtitle}</p>}
      </div>
      <div className="flex items-center gap-2">
        {actions}
        <ThemeToggle />
        <NotificationBell iconSize={20} />
      </div>
    </header>
  );
}

export default DesktopHeader;
