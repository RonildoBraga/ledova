import { BellIcon, XIcon } from '@phosphor-icons/react';
import { Popover, PopoverButton, PopoverPanel } from '@headlessui/react';
import { formatDateTime } from '@ledova/shared-utils';
import { useNotifications } from '@hooks/useNotifications';
import type { Notification } from '@ledova/shared-types';
import { DESIGN_TOKENS } from '@ledova/shared-constants';

const ICON_SM = DESIGN_TOKENS.icon.sizes.sm;

interface NotificationBellProps {
  iconSize?: number;
  className?: string;
}

function NotificationItem({
  notification,
  onRead,
  onArchive,
}: {
  notification: Notification;
  onRead: (uuid: string) => void;
  onArchive: (uuid: string) => void;
}) {
  return (
    <div className="group relative flex items-start gap-3 px-4 py-3 hover:bg-surface-raised/50 transition-colors border-b border-border-subtle/30 last:border-b-0">
      <button
        onClick={() => {
          if (!notification.isRead) onRead(notification.uuid);
        }}
        className="flex-1 min-w-0 text-left flex items-start gap-3"
      >
        {!notification.isRead && <span className="mt-1.5 h-2 w-2 rounded-full bg-brand-mid flex-shrink-0" />}
        <div className={`min-w-0 flex-1 ${notification.isRead ? 'pl-5' : ''}`}>
          <p className="text-sm font-medium text-text-primary truncate pr-6">{notification.title}</p>
          <p className="text-xs text-text-muted line-clamp-2 mt-0.5">{notification.body}</p>
          <p className="text-xs text-text-muted/60 mt-1">{formatDateTime(notification.createdAt)}</p>
        </div>
      </button>
      <button
        onClick={(e) => {
          e.stopPropagation();
          onArchive(notification.uuid);
        }}
        className="absolute top-3 right-3 p-1 rounded-md text-text-muted/40 opacity-0 group-hover:opacity-100 hover:text-text-primary hover:bg-surface-raised transition-all"
        title="Dismiss"
      >
        <XIcon size={ICON_SM} />
      </button>
    </div>
  );
}

export function NotificationBell({ iconSize = 20, className }: NotificationBellProps) {
  const {
    unreadCount,
    notifications,
    isLoadingNotifications,
    fetchNotifications,
    markAsRead,
    archive,
    markAllAsRead,
    isMarkingAllRead,
  } = useNotifications();

  const badgeText = unreadCount > 99 ? '99+' : String(unreadCount);

  return (
    <Popover className={`relative ${className ?? ''}`}>
      <PopoverButton
        onClick={() => fetchNotifications()}
        className="relative inline-flex items-center justify-center w-10 h-10 rounded-full text-text-muted hover:text-text-primary hover:bg-surface-raised/50 focus:outline-none focus:ring-2 focus:ring-brand-mid/30 transition-all duration-200"
      >
        <BellIcon weight="duotone" size={iconSize} aria-hidden="true" />
        {unreadCount > 0 && (
          <span className="absolute -top-0.5 -right-0.5 flex items-center justify-center min-w-[18px] h-[18px] px-1 text-[10px] font-bold text-white bg-error rounded-full">
            {badgeText}
          </span>
        )}
      </PopoverButton>

      <PopoverPanel
        transition
        className="absolute z-50 right-0 mt-2 w-80 rounded-xl bg-surface-overlay/95 backdrop-blur-md shadow-2xl shadow-black/20 border border-border-subtle/50 overflow-hidden transition data-[closed]:scale-95 data-[closed]:opacity-0 data-[enter]:duration-200 data-[leave]:duration-100"
      >
        <div className="flex items-center justify-between px-4 py-3 border-b border-border-subtle/30">
          <span className="text-sm font-medium text-text-primary">Notifications</span>
          {unreadCount > 0 && (
            <button
              onClick={() => markAllAsRead()}
              disabled={isMarkingAllRead}
              className="text-xs text-brand-light hover:text-brand-subtle disabled:opacity-50 transition-colors"
            >
              Mark all as read
            </button>
          )}
        </div>

        <div className="max-h-96 overflow-y-auto">
          {isLoadingNotifications && notifications.length === 0 ? (
            <div className="px-4 py-8 text-center text-sm text-text-muted">Loading...</div>
          ) : notifications.length === 0 ? (
            <div className="px-4 py-8 text-center text-sm text-text-muted">No notifications yet</div>
          ) : (
            notifications.map((notification) => (
              <NotificationItem
                key={notification.uuid}
                notification={notification}
                onRead={markAsRead}
                onArchive={archive}
              />
            ))
          )}
        </div>
      </PopoverPanel>
    </Popover>
  );
}

export default NotificationBell;
