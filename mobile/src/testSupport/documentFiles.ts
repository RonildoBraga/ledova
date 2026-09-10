interface Entry {
  size: number;
  content: string;
}

export const files = new Map<string, Entry>();
export const unreadable = new Set<string>();
export const sticky = new Set<string>();
export const operations: { kind: string; uri: string }[] = [];
export const nativeBehavior = { copyOnMove: false, failManagedConstruction: false };
export const cache = 'file:///private/cache/';

function join(parts: (string | { uri: string })[]) {
  return parts.map((part) => (typeof part === 'string' ? part : part.uri).replace(/\/$/, '')).join('/');
}

class File {
  uri: string;

  constructor(...parts: (string | { uri: string })[]) {
    this.uri = join(parts);
    if (nativeBehavior.failManagedConstruction && this.uri.includes('/ledova-upload-copies-v1/')) {
      throw new Error('Synthetic native file construction failed');
    }
  }

  get exists() {
    return !unreadable.has(this.uri) && files.has(this.uri);
  }

  info() {
    operations.push({ kind: 'info', uri: this.uri });
    if (unreadable.has(this.uri)) throw new Error('Synthetic file access refused');
    return { exists: files.has(this.uri), size: files.get(this.uri)?.size, uri: this.uri };
  }

  delete() {
    operations.push({ kind: 'delete', uri: this.uri });
    if (unreadable.has(this.uri) || !files.has(this.uri)) throw new Error('Synthetic deletion refused');
    if (!sticky.has(this.uri)) files.delete(this.uri);
  }

  move(destination: File) {
    operations.push({ kind: 'move', uri: this.uri });
    const entry = files.get(this.uri);
    if (!entry || files.has(destination.uri)) throw new Error('Synthetic move refused');
    files.set(destination.uri, { ...entry });
    if (!nativeBehavior.copyOnMove) files.delete(this.uri);
    this.uri = destination.uri;
  }
}

class Directory {
  uri: string;

  constructor(...parts: (string | { uri: string })[]) {
    this.uri = join(parts) + '/';
  }

  create() {}

  list() {
    throw new Error('Directory enumeration is not part of the cleanup contract');
  }
}

export const nativeFileSystem = { File, Directory, Paths: { cache: new Directory(cache) } };

export function pickedFile(id = 1, size = 5) {
  const uri = `${cache}DocumentPicker/00000000-0000-0000-0000-${String(id).padStart(12, '0')}.pdf`;
  files.set(uri, { size, content: `document-${id}` });
  return {
    canceled: false as const,
    assets: [{ uri, name: `${id}.pdf`, mimeType: 'application/pdf', size, lastModified: 0 }],
  };
}

export function resetFiles() {
  files.clear();
  unreadable.clear();
  sticky.clear();
  operations.length = 0;
  nativeBehavior.copyOnMove = false;
  nativeBehavior.failManagedConstruction = false;
}
