"""Minimal NBT (Named Binary Tag) reader/writer - stdlib only.

Supports just the tag types needed for servers.dat:
  TAG_End(0), TAG_Byte(1), TAG_Int(3), TAG_String(8), TAG_List(9),
  TAG_Compound(10)

NBT is big-endian. Strings are length-prefixed (unsigned short) modified-UTF8;
for the ASCII/typical names used here, plain UTF-8 is byte-compatible.

We represent tags in Python as:
  Compound -> dict[str, (type_id, value)]
  List     -> (element_type_id, [value, ...])
  String   -> str
  Byte/Int -> int

servers.dat is stored UNCOMPRESSED. Writing it gzipped will make Minecraft
silently ignore the file, so we never compress.
"""

import struct

TAG_END = 0
TAG_BYTE = 1
TAG_SHORT = 2
TAG_INT = 3
TAG_LONG = 4
TAG_FLOAT = 5
TAG_DOUBLE = 6
TAG_BYTE_ARRAY = 7
TAG_STRING = 8
TAG_LIST = 9
TAG_COMPOUND = 10


class _Reader:
    def __init__(self, data):
        self.data = data
        self.pos = 0

    def read(self, n):
        b = self.data[self.pos:self.pos + n]
        if len(b) != n:
            raise ValueError("unexpected end of NBT data")
        self.pos += n
        return b

    def u1(self):
        return self.read(1)[0]

    def i1(self):
        return struct.unpack(">b", self.read(1))[0]

    def u2(self):
        return struct.unpack(">H", self.read(2))[0]

    def i4(self):
        return struct.unpack(">i", self.read(4))[0]

    def string(self):
        length = self.u2()
        return self.read(length).decode("utf-8", errors="replace")

    def payload(self, tag_type):
        if tag_type == TAG_BYTE:
            return self.i1()
        if tag_type == TAG_SHORT:
            return struct.unpack(">h", self.read(2))[0]
        if tag_type == TAG_INT:
            return self.i4()
        if tag_type == TAG_LONG:
            return struct.unpack(">q", self.read(8))[0]
        if tag_type == TAG_FLOAT:
            return struct.unpack(">f", self.read(4))[0]
        if tag_type == TAG_DOUBLE:
            return struct.unpack(">d", self.read(8))[0]
        if tag_type == TAG_BYTE_ARRAY:
            n = self.i4()
            return self.read(n)
        if tag_type == TAG_STRING:
            return self.string()
        if tag_type == TAG_LIST:
            elem_type = self.u1()
            n = self.i4()
            return (elem_type, [self.payload(elem_type) for _ in range(n)])
        if tag_type == TAG_COMPOUND:
            out = {}
            while True:
                t = self.u1()
                if t == TAG_END:
                    break
                name = self.string()
                out[name] = (t, self.payload(t))
            return out
        raise ValueError(f"unsupported NBT tag type {tag_type}")


def _write_string(buf, s):
    encoded = s.encode("utf-8")
    buf += struct.pack(">H", len(encoded))
    buf += encoded


def _write_payload(buf, tag_type, value):
    if tag_type == TAG_BYTE:
        buf += struct.pack(">b", value)
    elif tag_type == TAG_SHORT:
        buf += struct.pack(">h", value)
    elif tag_type == TAG_INT:
        buf += struct.pack(">i", value)
    elif tag_type == TAG_LONG:
        buf += struct.pack(">q", value)
    elif tag_type == TAG_FLOAT:
        buf += struct.pack(">f", value)
    elif tag_type == TAG_DOUBLE:
        buf += struct.pack(">d", value)
    elif tag_type == TAG_BYTE_ARRAY:
        buf += struct.pack(">i", len(value))
        buf += bytes(value)
    elif tag_type == TAG_STRING:
        _write_string(buf, value)
    elif tag_type == TAG_LIST:
        elem_type, items = value
        # An empty list conventionally uses TAG_End as the element type.
        if not items:
            elem_type = TAG_END
        buf += struct.pack(">B", elem_type)
        buf += struct.pack(">i", len(items))
        for item in items:
            _write_payload(buf, elem_type, item)
    elif tag_type == TAG_COMPOUND:
        for name, (t, v) in value.items():
            buf += struct.pack(">B", t)
            _write_string(buf, name)
            _write_payload(buf, t, v)
        buf += struct.pack(">B", TAG_END)
    else:
        raise ValueError(f"unsupported NBT tag type {tag_type}")


def parse(data):
    """Parse uncompressed NBT bytes. Returns (root_name, (type, value))."""
    r = _Reader(data)
    t = r.u1()
    if t == TAG_END:
        return "", (TAG_END, None)
    name = r.string()
    return name, (t, r.payload(t))


def write(root_name, root_type, root_value):
    """Serialize a root tag to uncompressed NBT bytes."""
    buf = bytearray()
    buf += struct.pack(">B", root_type)
    _write_string(buf, root_name)
    _write_payload(buf, root_type, root_value)
    return bytes(buf)
