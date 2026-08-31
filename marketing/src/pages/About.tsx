const STATUS = [
  { label: 'License', value: 'Apache-2.0' },
  { label: 'Environment', value: 'Local + testnet' },
  { label: 'Security review', value: 'Not audited' },
  { label: 'Service status', value: 'No hosted service' },
];

export function About() {
  return (
    <>
      <section className="pb-16 pt-24 lg:pt-32">
        <div className="mx-auto max-w-6xl px-6">
          <div className="mx-auto max-w-3xl text-center">
            <h1 className="text-4xl font-bold text-text-primary sm:text-5xl">About Ledova</h1>
            <p className="mt-6 text-lg leading-relaxed text-text-muted">
              Ledova is experimental open-source software for exploring self-custody interfaces and token-contract
              designs. It is a developer project, not a company, exchange, issuer, or financial service.
            </p>
          </div>
        </div>
      </section>

      <section className="border-t border-border-subtle bg-surface-raised/50 py-24">
        <div className="mx-auto max-w-3xl px-6">
          <h2 className="text-center text-3xl font-bold text-text-primary">What the repository contains</h2>
          <div className="mt-10 space-y-8 text-base leading-relaxed text-text-muted">
            <p>A backend, web dashboard, mobile client, marketing shell, shared packages, and example contracts.</p>
            <p>
              The code may reference optional third-party integrations, but no provider account, production deployment,
              reserves, custody, or regulated service is included.
            </p>
            <p>Use local development networks or supported public testnets, synthetic data, and disposable keys.</p>
          </div>
        </div>
      </section>

      <section className="border-t border-border-subtle py-24">
        <div className="mx-auto max-w-6xl px-6">
          <h2 className="text-center text-3xl font-bold text-text-primary">Current status</h2>
          <div className="mt-10 grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
            {STATUS.map((item) => (
              <div key={item.label} className="rounded-xl border border-border-subtle bg-surface-raised/60 p-4">
                <p className="text-xs text-text-muted">{item.label}</p>
                <p className="mt-1 text-sm font-semibold text-text-primary">{item.value}</p>
              </div>
            ))}
          </div>
        </div>
      </section>
    </>
  );
}
