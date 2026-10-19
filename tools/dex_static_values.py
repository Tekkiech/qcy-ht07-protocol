#!/usr/bin/env python3
"""
Minimal DEX parser: extract static-field initial values (the encoded
static_values array) for named classes. Read-only; takes dex paths + class
descriptors as args. Used to recover QCY `static final byte CMDID_*` / `SOF`
constants that JADX inlines and does not emit in <clinit>.
"""
import sys, struct

def uleb128(data, off):
    result = 0; shift = 0
    while True:
        b = data[off]; off += 1
        result |= (b & 0x7f) << shift
        if not (b & 0x80): break
        shift += 7
    return result, off

def sleb128(data, off):
    result = 0; shift = 0
    while True:
        b = data[off]; off += 1
        result |= (b & 0x7f) << shift
        shift += 7
        if not (b & 0x80):
            if b & 0x40:
                result |= -(1 << shift)
            break
    return result, off

class Dex:
    def __init__(self, path):
        self.d = open(path, 'rb').read()
        d = self.d
        if d[:4] not in (b'dex\n',):
            # some multidex still start with dex\n
            pass
        self.string_ids_size = struct.unpack_from('<I', d, 0x38)[0]
        self.string_ids_off  = struct.unpack_from('<I', d, 0x3c)[0]
        self.type_ids_size   = struct.unpack_from('<I', d, 0x40)[0]
        self.type_ids_off    = struct.unpack_from('<I', d, 0x44)[0]
        self.proto_ids_size  = struct.unpack_from('<I', d, 0x48)[0]
        self.proto_ids_off   = struct.unpack_from('<I', d, 0x4c)[0]
        self.field_ids_size  = struct.unpack_from('<I', d, 0x50)[0]
        self.field_ids_off   = struct.unpack_from('<I', d, 0x54)[0]
        self.method_ids_size = struct.unpack_from('<I', d, 0x58)[0]
        self.method_ids_off  = struct.unpack_from('<I', d, 0x5c)[0]
        self.class_defs_size = struct.unpack_from('<I', d, 0x60)[0]
        self.class_defs_off  = struct.unpack_from('<I', d, 0x64)[0]

    def string(self, idx):
        d = self.d
        off = struct.unpack_from('<I', d, self.string_ids_off + idx*4)[0]
        _, off = uleb128(d, off)  # utf16 length
        end = d.index(b'\x00', off)
        return d[off:end].decode('utf-8', 'replace')

    def type_str(self, type_idx):
        d = self.d
        sidx = struct.unpack_from('<I', d, self.type_ids_off + type_idx*4)[0]
        return self.string(sidx)

    def field(self, field_idx):
        # field_id_item: ushort class_idx, ushort type_idx, uint name_idx
        d = self.d
        base = self.field_ids_off + field_idx*8
        class_idx, type_idx, name_idx = struct.unpack_from('<HHI', d, base)
        return self.type_str(class_idx), self.type_str(type_idx), self.string(name_idx)

    def find_class_def(self, descriptor):
        d = self.d
        for i in range(self.class_defs_size):
            base = self.class_defs_off + i*32
            class_idx = struct.unpack_from('<I', d, base)[0]
            if self.type_str(class_idx) == descriptor:
                class_data_off = struct.unpack_from('<I', d, base+24)[0]
                static_values_off = struct.unpack_from('<I', d, base+28)[0]
                return class_data_off, static_values_off
        return None

    def static_field_names(self, class_data_off):
        """Return list of (field_idx, name, type) for static fields, in order."""
        if class_data_off == 0:
            return []
        d = self.d; off = class_data_off
        sf, off = uleb128(d, off)
        inf, off = uleb128(d, off)
        sm, off = uleb128(d, off)
        vm, off = uleb128(d, off)
        res = []
        fidx = 0
        for _ in range(sf):
            diff, off = uleb128(d, off)
            _access, off = uleb128(d, off)
            fidx += diff
            cls, typ, name = self.field(fidx)
            res.append((name, typ))
        return res

    def parse_encoded_array(self, off):
        d = self.d
        size, off = uleb128(d, off)
        vals = []
        for _ in range(size):
            v, off = self.read_encoded_value(d, off)
            vals.append(v)
        return vals

    def read_encoded_value(self, d, off):
        arg_type = d[off]; off += 1
        vtype = arg_type & 0x1f
        varg = (arg_type >> 5) & 0x7
        n = varg + 1
        if vtype == 0x00:  # byte
            return (struct.unpack('<b', d[off:off+1])[0]), off+1
        if vtype in (0x02,0x03,0x04,0x06):  # short/char/int/long signed ints
            raw = d[off:off+n]; off += n
            val = int.from_bytes(raw, 'little', signed=True) if vtype in (0x02,0x04,0x06) else int.from_bytes(raw,'little')
            return val, off
        if vtype == 0x1f:  # boolean (value in varg)
            return bool(varg), off
        if vtype == 0x1e:  # null
            return None, off
        if vtype == 0x17:  # VALUE_STRING: n-byte string index
            sidx = int.from_bytes(d[off:off+n], 'little'); off += n
            return self.string(sidx), off
        # others: skip n bytes, return raw
        raw = d[off:off+n]; off += n
        return ('<t%02x>'%vtype, raw.hex()), off

def main():
    dexpaths = []
    classes = []
    for a in sys.argv[1:]:
        if a.startswith('L') and a.endswith(';'):
            classes.append(a)
        else:
            dexpaths.append(a)
    for cls in classes:
        found = False
        for p in dexpaths:
            try:
                dex = Dex(p)
            except Exception as e:
                continue
            cd = dex.find_class_def(cls)
            if not cd:
                continue
            found = True
            class_data_off, sv_off = cd
            names = dex.static_field_names(class_data_off)
            vals = dex.parse_encoded_array(sv_off) if sv_off else []
            print("== %s  (in %s) ==" % (cls, p.split('/')[-1]))
            for i,(name,typ) in enumerate(names):
                v = vals[i] if i < len(vals) else 0
                if isinstance(v,int):
                    disp = "%d (0x%02X)" % (v, v & 0xFF) if typ=='B' else "%d (0x%X)"%(v, v & 0xFFFFFFFF)
                else:
                    disp = repr(v)
                print("  %-22s %s = %s" % (name, typ, disp))
            break
        if not found:
            print("== %s : NOT FOUND ==" % cls)

if __name__ == '__main__':
    main()
