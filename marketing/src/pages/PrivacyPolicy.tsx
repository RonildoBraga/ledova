export function PrivacyPolicy() {
  return (
    <>
      <section className="pb-16 pt-24 lg:pt-32">
        <div className="mx-auto max-w-3xl px-6 text-center">
          <h1 className="text-4xl font-bold text-text-primary sm:text-5xl">Developer preview privacy notice</h1>
          <p className="mt-4 text-lg text-text-muted">For the open-source repository, not a hosted service</p>
        </div>
      </section>
      <section className="border-t border-border-subtle bg-surface-raised/50 py-24">
        <div className="mx-auto max-w-3xl space-y-8 px-6 leading-relaxed text-text-muted">
          <p>
            Ledova is experimental software. The project does not provide a hosted production service and does not
            collect personal information merely because you download or run the source code.
          </p>
          <div>
            <h2 className="text-xl font-semibold text-text-primary">Run it safely</h2>
            <p className="mt-2">
              Use synthetic data and disposable credentials. Do not submit real identity documents, financial data,
              private keys, or personal information to a development deployment.
            </p>
          </div>
          <div>
            <h2 className="text-xl font-semibold text-text-primary">Self-hosted deployments</h2>
            <p className="mt-2">
              Anyone who deploys or modifies the software is responsible for their own data practices, provider
              agreements, security controls, notices, retention rules, and applicable law.
            </p>
          </div>
          <p>This template is informational and is not legal advice or a privacy policy for your deployment.</p>
        </div>
      </section>
    </>
  );
}
