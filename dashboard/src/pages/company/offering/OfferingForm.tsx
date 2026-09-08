import { useState } from 'react';
import { Panel } from '@components/Panel';
import { OFFERING_EXEMPTION_LABELS } from '@ledova/shared';
import type {
  CompanyShareToken,
  Offering,
  OfferingExemption,
  OfferingInput,
  OperatorSettlementAsset,
} from '@ledova/shared';

const EXEMPTIONS = Object.entries(OFFERING_EXEMPTION_LABELS) as [OfferingExemption, string][];

const FIELD_CLASS =
  'mt-1 w-full rounded-lg border border-border bg-surface-raised px-3 py-2 text-sm text-text-primary ' +
  'placeholder:text-text-muted focus:border-brand-mid focus:outline-none focus:ring-1 focus:ring-brand-mid';

interface OfferingFormProps {
  tokens: CompanyShareToken[];
  busy: boolean;
  settlementAssets: OperatorSettlementAsset[];
  onCreate: (input: OfferingInput) => void;
  editing?: Offering;
  onUpdate?: (input: OfferingInput) => void;
  onCancelEdit?: () => void;
}

function localInput(iso: string | null | undefined): string {
  if (!iso) return '';
  const at = new Date(iso);
  if (Number.isNaN(at.getTime())) return '';
  const pad = (value: number) => String(value).padStart(2, '0');
  return `${at.getFullYear()}-${pad(at.getMonth() + 1)}-${pad(at.getDate())}T${pad(at.getHours())}:${pad(at.getMinutes())}`;
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="text-sm font-medium text-text-primary">{label}</span>
      {children}
    </label>
  );
}

export function OfferingForm({
  tokens,
  busy,
  settlementAssets,
  onCreate,
  editing,
  onUpdate,
  onCancelEdit,
}: OfferingFormProps) {
  const [token, setToken] = useState(editing?.tokenUuid ?? '');
  const [exemption, setExemption] = useState<OfferingExemption>(editing?.exemption ?? 's708_11_professional');
  const [pricePerShare, setPricePerShare] = useState(editing?.pricePerShare ?? '');
  const [minimumShares, setMinimumShares] = useState(editing ? String(editing.minimumShares) : '');
  const [targetShares, setTargetShares] = useState(editing ? String(editing.targetShares) : '');
  const [capShares, setCapShares] = useState(editing ? String(editing.capShares) : '');
  const [opensAt, setOpensAt] = useState(localInput(editing?.opensAt));
  const [closesAt, setClosesAt] = useState(localInput(editing?.closesAt));
  const [summary, setSummary] = useState(editing?.summary ?? '');
  const [useOfProceeds, setUseOfProceeds] = useState(editing?.useOfProceeds ?? '');
  const [acceptsBankTransfer, setAcceptsBankTransfer] = useState(editing?.acceptsBankTransfer ?? true);
  const [chosenAssets, setChosenAssets] = useState<string[]>(editing?.settlementAssets ?? []);

  const chosenToken = token || tokens[0]?.uuid || '';
  const hasARail = acceptsBankTransfer || chosenAssets.length > 0;
  const isComplete = Boolean(
    chosenToken && pricePerShare && minimumShares && targetShares && capShares && opensAt && hasARail,
  );

  const toggleAsset = (uuid: string) =>
    setChosenAssets((chosen) => (chosen.includes(uuid) ? chosen.filter((each) => each !== uuid) : [...chosen, uuid]));

  const handleSubmit = () => {
    const input: OfferingInput = {
      token: chosenToken,
      exemption,
      pricePerShare,
      acceptsBankTransfer,
      settlementAssets: chosenAssets,
      minimumShares: Number(minimumShares),
      targetShares: Number(targetShares),
      capShares: Number(capShares),
      opensAt: new Date(opensAt).toISOString(),
      closesAt: closesAt ? new Date(closesAt).toISOString() : null,
      summary,
      useOfProceeds,
    };
    if (editing && onUpdate) {
      onUpdate(input);
      return;
    }
    onCreate(input);
  };

  if (!editing && tokens.length === 0) {
    return (
      <Panel title="New Offering">
        <div className="px-2 py-6 text-sm text-text-muted">
          Deploy a share class before you offer it. An offering names one deployed share class and the shares it may
          issue against it.
        </div>
      </Panel>
    );
  }

  return (
    <Panel title={editing ? `Edit ${editing.tokenSymbol} offering` : 'New Offering'}>
      <div className="px-2 py-2 grid gap-4 sm:grid-cols-2">
        <Field label="Share class">
          <select value={chosenToken} onChange={(e) => setToken(e.target.value)} className={FIELD_CLASS}>
            {tokens.map((item) => (
              <option key={item.uuid} value={item.uuid}>
                {item.name} ({item.symbol})
              </option>
            ))}
          </select>
        </Field>

        <Field label="Exemption relied on">
          <select
            value={exemption}
            onChange={(e) => setExemption(e.target.value as OfferingExemption)}
            className={FIELD_CLASS}
          >
            {EXEMPTIONS.map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </Field>

        <Field label="Price per share (AUD)">
          <input
            value={pricePerShare}
            onChange={(e) => setPricePerShare(e.target.value)}
            inputMode="decimal"
            placeholder="2.50"
            className={FIELD_CLASS}
          />
        </Field>

        <Field label="Minimum shares">
          <input
            value={minimumShares}
            onChange={(e) => setMinimumShares(e.target.value)}
            inputMode="numeric"
            placeholder="1000"
            className={FIELD_CLASS}
          />
        </Field>

        <Field label="Target shares">
          <input
            value={targetShares}
            onChange={(e) => setTargetShares(e.target.value)}
            inputMode="numeric"
            placeholder="50000"
            className={FIELD_CLASS}
          />
        </Field>

        <Field label="Cap shares">
          <input
            value={capShares}
            onChange={(e) => setCapShares(e.target.value)}
            inputMode="numeric"
            placeholder="100000"
            className={FIELD_CLASS}
          />
        </Field>

        <Field label="Opens at">
          <input
            type="datetime-local"
            value={opensAt}
            onChange={(e) => setOpensAt(e.target.value)}
            className={FIELD_CLASS}
          />
        </Field>

        <Field label="Closes at (optional)">
          <input
            type="datetime-local"
            value={closesAt}
            onChange={(e) => setClosesAt(e.target.value)}
            className={FIELD_CLASS}
          />
        </Field>

        <div className="sm:col-span-2">
          <Field label="Summary">
            <textarea
              value={summary}
              onChange={(e) => setSummary(e.target.value)}
              rows={3}
              placeholder="What eligible investors are being offered"
              className={FIELD_CLASS}
            />
          </Field>
        </div>

        <div className="sm:col-span-2">
          <Field label="Use of proceeds">
            <textarea
              value={useOfProceeds}
              onChange={(e) => setUseOfProceeds(e.target.value)}
              rows={3}
              placeholder="What the money raised will be spent on"
              className={FIELD_CLASS}
            />
          </Field>
        </div>

        <div className="sm:col-span-2 space-y-2">
          <span className="text-sm font-medium text-text-primary">How investors may pay</span>

          <label className="flex items-center gap-3">
            <input
              type="checkbox"
              checked={acceptsBankTransfer}
              onChange={(e) => setAcceptsBankTransfer(e.target.checked)}
              className="h-4 w-4 rounded border-border"
            />
            <span className="text-sm text-text-primary">Accept bank transfer</span>
          </label>

          {settlementAssets.length === 0 ? (
            <p className="text-sm text-text-muted">
              The operator has not configured a settlement asset, so this offering can take bank transfer only.
            </p>
          ) : (
            settlementAssets.map((asset) => (
              <label key={asset.uuid} className="flex items-center gap-3">
                <input
                  type="checkbox"
                  checked={chosenAssets.includes(asset.uuid)}
                  onChange={() => toggleAsset(asset.uuid)}
                  className="h-4 w-4 rounded border-border"
                />
                <span className="text-sm text-text-primary">{asset.symbol}</span>
              </label>
            ))
          )}

          {!hasARail && (
            <p className="text-sm text-status-danger">
              Choose at least one way to be paid. An offering nobody can pay for cannot be submitted.
            </p>
          )}
        </div>

        <div className="sm:col-span-2 flex items-center justify-end gap-4">
          {editing && (
            <>
              <p className="mr-auto text-sm text-text-muted">
                {editing.status === 'rejected'
                  ? 'Rejected offerings are editable. Submitting it again sends it back for review.'
                  : 'Draft offerings are editable. Submitting it for review locks it.'}
              </p>
              <button
                onClick={onCancelEdit}
                disabled={busy}
                className="text-sm font-medium text-text-muted hover:text-text-primary disabled:opacity-50 transition-colors"
              >
                Cancel
              </button>
            </>
          )}
          <button
            onClick={handleSubmit}
            disabled={!isComplete || busy}
            className="rounded-lg bg-brand-mid hover:bg-brand disabled:bg-surface-disabled disabled:cursor-not-allowed px-6 py-2.5 text-sm font-semibold text-white transition-colors"
          >
            {editing ? 'Save changes' : 'Create draft offering'}
          </button>
        </div>
      </div>
    </Panel>
  );
}
