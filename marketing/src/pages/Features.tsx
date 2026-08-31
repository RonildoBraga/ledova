const FEATURES = [
  {
    title: 'Wallet interface examples',
    description:
      'Reference flows for wallet connection and transaction preparation. Use disposable development keys only.',
  },
  {
    title: 'Portfolio views',
    description: 'Example charts, balances, and activity views intended for synthetic or public-testnet data.',
  },
  {
    title: 'Contract examples',
    description: 'Unaudited token, allowlist, and atomic-swap contracts with no identified live deployment.',
  },
  {
    title: 'Multi-platform clients',
    description: 'Web and mobile code that can be configured against a developer-operated backend.',
  },
];

export function Features() {
  return (
    <>
      <section className="pb-16 pt-24 lg:pt-32">
        <div className="mx-auto max-w-6xl px-6 text-center">
          <h1 className="text-4xl font-bold text-text-primary sm:text-5xl">Project features</h1>
          <p className="mt-4 text-lg text-text-muted">
            Experimental building blocks for local development and public testnets.
          </p>
        </div>
      </section>
      <section className="pb-24">
        <div className="mx-auto grid max-w-6xl gap-6 px-6 sm:grid-cols-2">
          {FEATURES.map((feature) => (
            <div key={feature.title} className="rounded-2xl border border-border-subtle bg-surface-base/80 p-6">
              <h2 className="text-lg font-semibold text-text-primary">{feature.title}</h2>
              <p className="mt-2 text-text-muted">{feature.description}</p>
            </div>
          ))}
        </div>
      </section>
    </>
  );
}
