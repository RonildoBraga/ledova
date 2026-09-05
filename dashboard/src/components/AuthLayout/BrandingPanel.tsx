import { ShieldCheckIcon, CubeIcon, ChartBarIcon } from '@phosphor-icons/react';
import { DESIGN_TOKENS } from '@ledova/shared';
import { useColors } from '@hooks/useColors';

const ICON_SM = DESIGN_TOKENS.icon.sizes.sm;

const highlights = [
  {
    icon: ChartBarIcon,
    title: 'Portfolio Tracking',
    description: 'Monitor all your assets in real-time',
  },
  {
    icon: CubeIcon,
    title: 'Air-Gapped Signing',
    description: 'Hardware wallet support for maximum security',
  },
  {
    icon: ShieldCheckIcon,
    title: 'Non-Custodial',
    description: 'Your keys, your assets',
  },
];

export function BrandingPanel() {
  const colors = useColors();

  return (
    <div className="relative w-full bg-surface-raised flex flex-col justify-center items-center p-12 overflow-hidden">
      <div className="absolute inset-0 bg-gradient-to-br from-brand-mid/10 via-transparent to-brand/5 pointer-events-none" />

      <div className="absolute top-1/4 right-0 w-64 h-64 bg-brand-mid/10 rounded-full blur-3xl" />
      <div className="absolute bottom-1/4 left-0 w-48 h-48 bg-brand-light/10 rounded-full blur-3xl" />

      <div className="relative z-10 max-w-md text-center space-y-8">
        <div className="space-y-4">
          <h2 className="text-3xl font-bold text-text-primary">
            Your assets,
            <br />
            <span className="text-brand-mid">your control</span>
          </h2>
          <p className="text-text-secondary">A smart wallet that puts you in charge of your digital assets.</p>
        </div>

        <div className="relative mx-auto">
          <img
            src="/images/app-screenshot-portfolio.png"
            alt="Ledova app"
            className="w-48 h-auto rounded-[2rem] shadow-2xl border-4 border-surface-tertiary mx-auto"
          />
          <div className="absolute -top-3 -right-3 w-16 h-16 bg-brand-mid/10 rounded-full blur-xl" />
          <div className="absolute -bottom-3 -left-3 w-20 h-20 bg-brand-light/10 rounded-full blur-xl" />
        </div>

        <div className="space-y-3">
          {highlights.map((item) => (
            <div
              key={item.title}
              className="flex items-center gap-3 p-3 bg-surface-tertiary/50 rounded-xl border border-border/50"
            >
              <div className="p-2 bg-brand-mid/10 rounded-lg shrink-0">
                <item.icon size={ICON_SM} className="text-brand-mid" />
              </div>
              <div className="text-left">
                <p className="text-sm font-medium text-text-primary">{item.title}</p>
                <p className="text-xs text-text-muted">{item.description}</p>
              </div>
            </div>
          ))}
        </div>

        <div className="flex items-center justify-center gap-4 pt-2">
          <div className="flex items-center gap-1.5">
            <div
              className="w-6 h-6 rounded-full flex items-center justify-center"
              style={{ backgroundColor: `${colors.chain.bitcoin}1A` }}
            >
              <svg
                viewBox="0 0 24 24"
                className="w-3.5 h-3.5"
                style={{ color: colors.chain.bitcoin }}
                fill="currentColor"
              >
                <path d="M23.638 14.904c-1.602 6.43-8.113 10.34-14.542 8.736C2.67 22.05-1.244 15.525.362 9.105 1.962 2.67 8.475-1.243 14.9.358c6.43 1.605 10.342 8.115 8.738 14.546zm-6.35-4.613c.24-1.59-.974-2.45-2.64-3.03l.54-2.153-1.315-.33-.52 2.1c-.347-.087-.704-.17-1.06-.25l.53-2.12-1.317-.328-.54 2.15c-.286-.067-.567-.132-.84-.2l-1.815-.45-.35 1.407s.974.225.954.236c.533.136.63.486.613.766l-.614 2.46c.037.01.083.024.135.046l-.137-.035-.86 3.45c-.067.163-.237.41-.617.313.013.02-.955-.24-.955-.24l-.652 1.51 1.71.427c.318.08.63.163.936.242l-.546 2.19 1.315.33.54-2.16c.36.1.707.19 1.05.273l-.54 2.14 1.317.33.547-2.18c2.24.423 3.926.253 4.638-1.774.574-1.635-.028-2.58-1.21-3.196.86-.2 1.51-.766 1.68-1.93zm-3.01 4.22c-.404 1.64-3.157.75-4.05.53l.72-2.9c.896.224 3.757.67 3.33 2.37zm.41-4.24c-.37 1.49-2.662.735-3.405.55l.654-2.64c.744.186 3.137.534 2.75 2.09z" />
              </svg>
            </div>
            <span className="text-xs text-text-muted">Bitcoin</span>
          </div>
          <div className="flex items-center gap-1.5">
            <div
              className="w-6 h-6 rounded-full flex items-center justify-center"
              style={{ backgroundColor: `${colors.chain.ethereum}1A` }}
            >
              <svg
                viewBox="0 0 24 24"
                className="w-3.5 h-3.5"
                style={{ color: colors.chain.ethereum }}
                fill="currentColor"
              >
                <path d="M11.944 17.97L4.58 13.62 11.943 24l7.37-10.38-7.372 4.35h.003zM12.056 0L4.69 12.223l7.365 4.354 7.365-4.35L12.056 0z" />
              </svg>
            </div>
            <span className="text-xs text-text-muted">Ethereum</span>
          </div>
        </div>
      </div>
    </div>
  );
}
