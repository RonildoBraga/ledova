import json
import struct
import sys
import zipfile


expected = set(sys.argv[2].split(','))
found = set()
libraries = []
with zipfile.ZipFile(sys.argv[1]) as artifact:
    for name in artifact.namelist():
        if name.endswith('.dex') or name == 'assets/index.android.bundle':
            data = artifact.read(name)
            for marker in (b'org/example/ledova/releaseprobe/ScannerReleaseTest', b'scanner-probe-cover'):
                if marker in data:
                    raise SystemExit(f'An ordinary Release artifact contains scanner test code: {name}')
    for name in artifact.namelist():
        if not name.startswith('lib/') or not name.endswith('.so'):
            continue
        architecture = name.split('/')[1]
        found.add(architecture)
        data = artifact.read(name)
        if data[:4] != b'\x7fELF' or data[5] != 1:
            raise SystemExit(f'Unsupported ELF encoding: {name}')
        if data[4] == 2:
            offset = struct.unpack_from('<Q', data, 32)[0]
            entry_size, count = struct.unpack_from('<HH', data, 54)
            segment_format = '<IIQQQQQQ'
        elif data[4] == 1:
            offset = struct.unpack_from('<I', data, 28)[0]
            entry_size, count = struct.unpack_from('<HH', data, 42)
            segment_format = '<IIIIIIII'
        else:
            raise SystemExit(f'Unsupported ELF class: {name}')
        alignments = []
        for index in range(count):
            segment = struct.unpack_from(segment_format, data, offset + index * entry_size)
            if segment[0] != 1:
                continue
            file_offset, virtual_address = segment[2:4] if data[4] == 2 else segment[1:3]
            alignment = segment[-1]
            if alignment < 16384 or (virtual_address - file_offset) % 16384:
                raise SystemExit(f'Native library does not support 16 KiB pages: {name}')
            alignments.append(alignment)
        if not alignments:
            raise SystemExit(f'ELF has no loadable segments: {name}')
        libraries.append({'path': name, 'minimum_load_alignment': min(alignments)})
if found != expected:
    raise SystemExit(f'Expected native architectures {sorted(expected)}, found {sorted(found)}')
print(json.dumps({'architectures': sorted(found), 'libraries': libraries}, indent=2))
