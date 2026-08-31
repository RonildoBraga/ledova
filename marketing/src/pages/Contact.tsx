import { Info as InfoIcon } from '@phosphor-icons/react';

export function Contact() {
  return (
    <>
      <section className="pb-16 pt-24 lg:pt-32">
        <div className="mx-auto max-w-6xl px-6">
          <div className="mx-auto max-w-3xl text-center">
            <h1 className="text-4xl font-bold text-text-primary sm:text-5xl">Contact Us</h1>
            <p className="mt-4 text-lg text-text-muted">
              Deployment and support are provided by each environment owner.
            </p>
          </div>
        </div>
      </section>

      <section className="border-t border-border-subtle bg-surface-raised/50 py-24">
        <div className="mx-auto max-w-2xl px-6">
          <div>
            <div className="rounded-2xl border border-border-subtle bg-surface-base/80 p-6 transition-colors hover:border-border">
              <div className="flex items-start gap-4">
                <div className="shrink-0 rounded-xl bg-brand/10 p-3">
                  <InfoIcon size={24} weight="duotone" className="text-brand-light" />
                </div>
                <div>
                  <h2 className="mb-2 text-lg font-semibold text-text-primary">Reference project</h2>
                  <p className="text-sm text-text-muted">
                    This source repository does not operate a hosted service, support desk, office, or regulated
                    business. A deployment owner must publish their own support and contact details.
                  </p>
                  <p className="mt-3 text-sm text-text-muted">
                    Questions about the open-source project itself:{' '}
                    <a href="mailto:hello@ledova.io" className="text-brand-light hover:underline">
                      hello@ledova.io
                    </a>{' '}
                    &middot; Code of Conduct reports:{' '}
                    <a href="mailto:conduct@ledova.io" className="text-brand-light hover:underline">
                      conduct@ledova.io
                    </a>
                  </p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>
    </>
  );
}
