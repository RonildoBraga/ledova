import * as DocumentPicker from 'expo-document-picker';
import { Directory, File, Paths } from 'expo-file-system';

const SLOT_COUNT = 16;
const MAX_DOCUMENT_BYTES = 10 * 1024 * 1024;
const PICKER_NAME = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}(\.[a-z0-9_-]{0,32})?$/i;
const copies = new Map<number, DocumentCopy>();
let picking = false;

class DocumentSelectionError extends Error {}

export interface UploadFile {
  uri: string;
  name: string;
  type: string;
}

function removeCopy(file: File): boolean {
  try {
    if (file.info().exists) file.delete();
    if (file.info().exists) throw new Error('Document copy remains.');
    return true;
  } catch {
    console.warn('Document cache cleanup did not complete.');
    return false;
  }
}

function managedFile(slot: number): File {
  return new File(Paths.cache, 'ledova-upload-copies-v1', `slot-${slot}`);
}

function availableSlot(): number {
  new Directory(Paths.cache, 'ledova-upload-copies-v1').create({ intermediates: true, idempotent: true });
  let available = -1;
  for (let slot = 0; slot < SLOT_COUNT; slot++) {
    const existing = copies.get(slot);
    if (existing) existing.cleanup();
    if (!copies.has(slot) && removeCopy(managedFile(slot)) && available < 0) available = slot;
  }
  if (available < 0)
    throw new DocumentSelectionError('Document storage is busy. Please finish an upload and try again.');
  return available;
}

export class DocumentCopy {
  private consumers = 0;
  private retired = false;

  constructor(
    readonly file: UploadFile,
    private readonly slot: number,
  ) {}

  acquire(): () => void {
    if (this.retired || copies.get(this.slot) !== this) throw new Error('Choose the document again.');
    try {
      if (!managedFile(this.slot).info().exists) throw new Error('Document copy is missing.');
    } catch {
      throw new Error('Choose the document again.');
    }
    this.consumers++;
    let released = false;
    return () => {
      if (released) return;
      released = true;
      this.consumers--;
      this.cleanup();
    };
  }

  retire(): void {
    this.retired = true;
    this.cleanup();
  }

  cleanup(): void {
    if (!this.retired || this.consumers || copies.get(this.slot) !== this) return;
    if (removeCopy(managedFile(this.slot))) copies.delete(this.slot);
  }
}

export async function pickDocumentCopy(
  isCurrent: () => boolean,
  chooseDocument = DocumentPicker.getDocumentAsync,
): Promise<DocumentCopy | null> {
  if (!isCurrent()) return null;
  if (picking) throw new Error('A document picker is already open.');
  picking = true;
  const originals: File[] = [];
  let destination: File | undefined;
  try {
    const slot = availableSlot();
    if (!isCurrent()) return null;
    const result = await chooseDocument({
      type: ['application/pdf', 'image/*'],
      copyToCacheDirectory: true,
      multiple: false,
    });
    if (result.canceled || !result.assets?.[0]) return null;
    const prefix = new Directory(Paths.cache, 'DocumentPicker').uri.replace(/\/?$/, '/');
    for (const uri of new Set(result.assets.map((asset) => asset.uri))) {
      if (uri.startsWith(prefix) && PICKER_NAME.test(uri.slice(prefix.length))) originals.push(new File(uri));
    }
    if (result.assets.length !== 1) throw new DocumentSelectionError('Please choose one document at a time.');
    const asset = result.assets[0];
    const original = originals[0];
    if (!original) {
      throw new DocumentSelectionError('Could not keep a private copy of this document. Please choose it again.');
    }
    if (!isCurrent()) return null;
    const info = original.info();
    if (!info.exists || !Number.isSafeInteger(info.size) || !info.size || info.size > MAX_DOCUMENT_BYTES) {
      throw new DocumentSelectionError('Choose a non-empty PDF or image no larger than 10 MB.');
    }
    if (asset.size !== undefined && asset.size !== info.size) {
      throw new DocumentSelectionError('The document copy is incomplete. Please choose it again.');
    }
    destination = managedFile(slot);
    new File(asset.uri).move(destination);
    if (!destination.info().exists || destination.info().size !== info.size) {
      throw new DocumentSelectionError('Could not keep a private copy of this document. Please choose it again.');
    }
    if (!removeCopy(original))
      throw new DocumentSelectionError('Could not retire the temporary document copy. Please try again.');
    originals.length = 0;
    const copy = new DocumentCopy(
      { uri: destination.uri, name: asset.name, type: asset.mimeType || 'application/octet-stream' },
      slot,
    );
    copies.set(slot, copy);
    destination = undefined;
    return copy;
  } catch (error) {
    if (error instanceof DocumentSelectionError) throw error;
    throw new DocumentSelectionError('Could not read the document. Please choose it again.');
  } finally {
    for (const original of originals) removeCopy(original);
    if (destination) removeCopy(destination);
    picking = false;
  }
}
