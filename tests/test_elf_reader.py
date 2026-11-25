import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import elf_reader
from memory_bus import read_bus_words, write_bus_words


class Segment:
    def __init__(self, address, data, size=None):
        self.fields = {"p_type": "PT_LOAD", "p_paddr": address,
                       "p_vaddr": address, "p_memsz": size or len(data)}
        self.payload = data

    def __getitem__(self, key):
        return self.fields[key]

    def data(self):
        return self.payload


class Section:
    def __init__(self, address, size, flags):
        self.fields = {"sh_addr": address, "sh_size": size, "sh_flags": flags}

    def __getitem__(self, key):
        return self.fields[key]


class Elf:
    def iter_segments(self):
        return iter((Segment(0x100000, b"\x13\x00\x00\x00", 0x100),
                     Segment(0x20008, b"\x01\x00\x00\x00")))

    def iter_sections(self):
        return iter((Section(0x100000, 0x80, 6),
                     Section(0x100080, 0x20, 6), Section(0x20008, 4, 3)))


def test_load_segments_preserves_addresses_and_zero_fills(tmp_path, monkeypatch):
    monkeypatch.setattr(elf_reader, "ELFFile", lambda source: Elf())
    path = tmp_path / "program.elf"
    path.write_bytes(b"fixture")
    memory = elf_reader.load_memory(4, path)
    assert memory[0x100000 // 4] == 0x13
    assert memory[(0x100000 + 4) // 4] == 0
    assert memory[0x20008 // 4] == 1
    assert memory[0] == 0
    assert read_bus_words(memory, 0x20008 // 4, 32) == 1
    write_bus_words(memory, 0x20008 // 4, 2, 0xf, 32)
    assert memory[0x20008 // 4] == 2
    assert elf_reader.get_text_section_addr(path) == (0x100000, 0x1000a0)
