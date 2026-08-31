import { useState, type ReactNode } from 'react';
import { CaretDownIcon } from '@phosphor-icons/react';
import { DESIGN_TOKENS } from '@ledova/shared-constants';

const ICON_MD = DESIGN_TOKENS.icon.sizes.md;

interface AccordionProps {
  title: string | ReactNode;
  icon?: ReactNode;
  /**
   * Optional actions to display on the right side of the header (next to the caret).
   */
  actions?: ReactNode;
  /**
   * Content to display when expanded.
   * NOTE: Do NOT add padding to children - Accordion handles all padding automatically
   * to ensure consistent alignment across all sections.
   */
  children: ReactNode;
  defaultExpanded?: boolean;
  /**
   * Visual variant:
   * - "card" (default): Standalone card with background, border, and rounded corners.
   * - "inline": No container styling — for nesting inside an existing card.
   */
  variant?: 'card' | 'inline';
}

export function Accordion({
  title,
  icon,
  actions,
  children,
  defaultExpanded = true,
  variant = 'card',
}: AccordionProps) {
  const [isExpanded, setIsExpanded] = useState(defaultExpanded);

  const isCard = variant === 'card';

  return (
    <div
      className={
        isCard
          ? 'bg-surface-raised rounded-xl border border-border overflow-hidden'
          : 'border-b border-border last:border-b-0'
      }
    >
      {/* Header */}
      <button
        type="button"
        className={`w-full flex items-center justify-between py-4 transition-colors gap-3 text-left ${
          isCard ? 'px-4 bg-surface-raised hover:bg-surface-tertiary/50' : 'hover:bg-surface-tertiary/30'
        }`}
        onClick={() => setIsExpanded(!isExpanded)}
        aria-expanded={isExpanded}
        aria-label={`${typeof title === 'string' ? title : 'Section'}, ${isExpanded ? 'expanded' : 'collapsed'}`}
      >
        <div className="flex items-center gap-3 flex-1 min-w-0">
          {icon && <span className="text-text-muted flex-shrink-0">{icon}</span>}
          {typeof title === 'string' ? (
            <span className={`text-text-primary truncate ${isCard ? 'text-lg font-semibold' : 'font-medium'}`}>
              {title}
            </span>
          ) : (
            title
          )}
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          {actions}
          <CaretDownIcon
            size={ICON_MD}
            className={`text-text-subtle transition-transform duration-200 ${isExpanded ? 'rotate-180' : ''}`}
          />
        </div>
      </button>

      {/* Content */}
      <div
        className={`transition-all duration-200 ease-in-out overflow-hidden ${
          isExpanded ? 'max-h-[2000px] opacity-100' : 'max-h-0 opacity-0'
        }`}
      >
        <div className={isCard ? 'px-4 pb-4' : 'pb-4'}>{children}</div>
      </div>
    </div>
  );
}
