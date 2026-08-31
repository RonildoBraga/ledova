import { Fragment, type ReactNode } from 'react';
import { Dialog, DialogPanel, Transition, TransitionChild } from '@headlessui/react';

interface ModalProps {
  isOpen: boolean;
  onClose: () => void;
  children: ReactNode;
  showFooter?: boolean;
  showCancelButton?: boolean;
  cancelLabel?: string;
  confirmLabel?: string;
  onCancel?: () => void;
  onConfirm?: () => void;
  confirmDisabled?: boolean;
  confirmLoading?: boolean;
  title?: ReactNode;
  size?: 'sm' | 'md' | 'lg' | 'xl' | '2xl' | '3xl';
  fullHeight?: boolean;
}

const sizeClasses = {
  sm: 'max-w-sm',
  md: 'max-w-md',
  lg: 'max-w-lg',
  xl: 'max-w-xl',
  '2xl': 'max-w-2xl',
  '3xl': 'max-w-3xl',
};

export function Modal({
  isOpen,
  onClose,
  children,
  showFooter = false,
  showCancelButton = true,
  cancelLabel = 'Cancel',
  confirmLabel = 'Confirm',
  onCancel,
  onConfirm,
  confirmDisabled = false,
  confirmLoading = false,
  title,
  size = 'md',
  fullHeight = false,
}: ModalProps) {
  return (
    <Transition appear show={isOpen} as={Fragment}>
      <Dialog as="div" className="relative z-50" onClose={onClose}>
        <TransitionChild
          as={Fragment}
          enter="ease-out duration-200"
          enterFrom="opacity-0"
          enterTo="opacity-100"
          leave="ease-in duration-100"
          leaveFrom="opacity-100"
          leaveTo="opacity-0"
        >
          <div className="fixed inset-0 bg-black/50 backdrop-blur-sm" />
        </TransitionChild>

        <div className="fixed inset-0 overflow-y-auto">
          <div className="flex min-h-full items-center justify-center p-4">
            <TransitionChild
              as={Fragment}
              enter="ease-out duration-200"
              enterFrom="opacity-0 scale-95"
              enterTo="opacity-100 scale-100"
              leave="ease-in duration-100"
              leaveFrom="opacity-100 scale-100"
              leaveTo="opacity-0 scale-95"
            >
              <DialogPanel
                className={`w-full ${sizeClasses[size]} transform overflow-hidden rounded-xl bg-surface-raised border border-border shadow-2xl transition-all`}
              >
                {title && (
                  <div className="px-4 pt-4 pb-2 border-b border-border-subtle">
                    <h3 className="text-lg font-semibold text-text-primary">{title}</h3>
                  </div>
                )}

                <div className={`p-4 ${fullHeight ? '' : 'max-h-[70vh]'} overflow-y-auto`}>{children}</div>

                {showFooter && (
                  <div className="flex gap-3 p-4 border-t border-border bg-surface-tertiary">
                    {showCancelButton && (
                      <button
                        type="button"
                        className={`flex-1 px-4 py-3 rounded-lg font-medium text-text-primary bg-surface-disabled border border-border hover:bg-surface-tertiary transition-colors ${
                          confirmLoading ? 'opacity-50 cursor-not-allowed' : ''
                        } ${!onConfirm ? 'flex-none w-full' : ''}`}
                        onClick={onCancel ?? onClose}
                        disabled={confirmLoading}
                      >
                        {cancelLabel}
                      </button>
                    )}
                    {onConfirm && (
                      <button
                        type="button"
                        className={`flex-1 px-4 py-3 rounded-lg font-semibold text-white transition-colors ${
                          confirmDisabled || confirmLoading
                            ? 'bg-surface-disabled opacity-50 cursor-not-allowed'
                            : 'bg-brand-light hover:bg-brand'
                        } ${!showCancelButton ? 'flex-none w-full' : ''}`}
                        onClick={onConfirm}
                        disabled={confirmDisabled || confirmLoading}
                      >
                        {confirmLoading ? 'Loading...' : confirmLabel}
                      </button>
                    )}
                  </div>
                )}
              </DialogPanel>
            </TransitionChild>
          </div>
        </div>
      </Dialog>
    </Transition>
  );
}
