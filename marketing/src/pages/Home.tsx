const AREAS = [
  {
    name: 'Self-custody interface',
    description:
      'Example portfolio, wallet, and signing flows for development with synthetic data and disposable keys.',
    link: '/features',
  },
  {
    name: 'AUDY design',
    description: 'An experimental token design with no issuer, reserves, redemption promise, or live deployment.',
    link: '/audy-whitepaper.html',
  },
  {
    name: 'AUSG design',
    description: 'An experimental reference-value token that is not a bond, security, investment, or government asset.',
    link: '/ausg-whitepaper.html',
  },
  {
    name: 'Share-token design',
    description: 'Example allowlist and atomic-swap mechanics with no legal ownership or investment rights.',
    link: '/share-tokens-whitepaper.html',
  },
];

export function Home() {
  return (
    <>
      <section className="relative">
        <div className="mx-auto max-w-6xl px-6 pb-16 pt-32 text-center lg:pb-24 lg:pt-44">
          <div className="mb-6 inline-flex rounded-full border border-amber-500/30 bg-amber-500/10 px-4 py-1.5 text-xs font-medium text-amber-400">
            Experimental • unaudited • local and public-testnet use only
          </div>
          <h1 className="mx-auto max-w-4xl text-4xl font-bold leading-tight tracking-tight text-text-primary sm:text-5xl lg:text-6xl">
            Explore digital-asset software
            <span className="block text-brand-light">without production claims</span>
          </h1>
          <p className="mx-auto mt-6 max-w-2xl text-lg text-text-muted lg:text-xl">
            Ledova is an open-source developer project. It does not operate a financial service, hold funds, issue
            assets, or identify any live contract deployment.
          </p>
        </div>
      </section>

      <section id="demo" className="border-t border-border-subtle py-24">
        <div className="mx-auto max-w-5xl px-6">
          <div className="text-center">
            <h2 className="text-3xl font-bold text-text-primary">See it in action</h2>
            <p className="mt-4 text-lg text-text-muted">
              A one-minute walkthrough of the local development stack: sign-up, onboarding, watch-only wallets, and live
              market data. Recorded against synthetic data — run it yourself with{' '}
              <code className="rounded bg-surface-raised px-1.5 py-0.5 text-sm text-brand-light">
                docker compose up
              </code>
              .
            </p>
          </div>
          <video
            className="mt-12 w-full rounded-2xl border border-border-subtle shadow-2xl"
            controls
            preload="none"
            poster="/demo/ledova-demo-poster.jpg"
          >
            <source src="/demo/ledova-demo.mp4" type="video/mp4" />
            <source src="/demo/ledova-demo.webm" type="video/webm" />
            Your browser does not support embedded video.
          </video>
        </div>
      </section>

      <section className="border-t border-border-subtle bg-surface-raised/50 py-24">
        <div className="mx-auto max-w-6xl px-6">
          <div className="text-center">
            <h2 className="text-3xl font-bold text-text-primary">Reference areas</h2>
            <p className="mt-4 text-lg text-text-muted">Use synthetic data, disposable keys, and test networks.</p>
          </div>
          <div className="mt-16 grid gap-8 lg:grid-cols-2">
            {AREAS.map((area) => (
              <a
                key={area.name}
                href={area.link}
                className="rounded-2xl border border-border-subtle bg-surface-base/80 p-8 transition-colors hover:border-border"
              >
                <h3 className="text-xl font-bold text-text-primary">{area.name}</h3>
                <p className="mt-3 text-text-muted">{area.description}</p>
                <p className="mt-5 text-sm font-medium text-brand-light">Read the experimental design note</p>
              </a>
            ))}
          </div>
        </div>
      </section>
    </>
  );
}
