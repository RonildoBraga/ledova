interface AddressLine {
  label: string;
  value: string;
}

export function parseAddress(address: string): { lines: AddressLine[] } {
  if (!address) return { lines: [] };
  const parts = address
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean);
  const labels = ['Street', 'City', 'State', 'Postcode', 'Country'];
  return {
    lines: parts.map((part, i) => ({ label: labels[i] || `Line ${i + 1}`, value: part })),
  };
}

export function getAddressDisplayLines(parsed: { lines: AddressLine[] }): AddressLine[] {
  return parsed.lines;
}
