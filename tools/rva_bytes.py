"""Print bytes at an RVA of a PE file: python rva_bytes.py <exe> <rva hex> [count]"""
import struct
import sys

data = open(sys.argv[1], "rb").read()
rva = int(sys.argv[2], 16)
count = int(sys.argv[3]) if len(sys.argv) > 3 else 32
pe = struct.unpack_from("<I", data, 0x3C)[0]
sections = struct.unpack_from("<H", data, pe + 6)[0]
optional = struct.unpack_from("<H", data, pe + 20)[0]
table = pe + 24 + optional
for i in range(sections):
    name, vsize, vaddr, rawsize, rawptr = struct.unpack_from("<8sIIII", data, table + 40 * i)
    if vaddr <= rva < vaddr + max(vsize, rawsize):
        off = rawptr + rva - vaddr
        print(name.rstrip(b"\0").decode(), " ".join(f"{b:02x}" for b in data[off:off + count]))
        break
