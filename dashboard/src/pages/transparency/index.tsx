export default function TransparencyPage() {
  return (
    <div className="mx-auto max-w-4xl px-4 py-12 sm:px-6 lg:px-8">
      <div className="rounded-2xl border border-amber-500/30 bg-amber-500/10 p-8 text-center">
        <p className="text-xs font-medium uppercase tracking-wide text-amber-400">Experimental view</p>
        <h1 className="mt-3 text-3xl font-bold text-text-primary">Transparency demo</h1>
        <p className="mx-auto mt-4 max-w-2xl text-text-muted">
          This open-source build does not identify a live token, reserve account, issuer, or contract deployment. Use
          this page only with synthetic data or contracts you deploy to a local network or supported public testnet.
        </p>
        <p className="mx-auto mt-3 max-w-2xl text-sm text-text-subtle">
          No reserve, price peg, redemption, financial-service, or production-readiness claim is made.
        </p>
      </div>
    </div>
  );
}
