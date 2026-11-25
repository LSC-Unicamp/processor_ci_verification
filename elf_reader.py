"""Read ELF load segments into a sparse, word-addressed simulation memory."""

from collections import defaultdict

from elftools.elf.elffile import ELFFile


def _load_segments(filename):
    memory = defaultdict(int)
    with open(filename, "rb") as source:
        elf = ELFFile(source)
        segments = [segment for segment in elf.iter_segments()
                    if segment["p_type"] == "PT_LOAD" and segment["p_memsz"]]
        if not segments:
            raise ValueError(f"ELF has no loadable segments: {filename}")
        for segment in segments:
            address = int(segment["p_paddr"] or segment["p_vaddr"])
            data = segment.data()
            size = int(segment["p_memsz"])
            if len(data) > size:
                raise ValueError(f"ELF segment exceeds declared memory size: {filename}")
            # Uninitialized segment bytes read as zero without allocating a
            # potentially huge stack or BSS range.
            for offset in range(len(data)):
                byte_address = address + offset
                word_address, lane = divmod(byte_address, 4)
                value = data[offset]
                mask = 0xff << (lane * 8)
                memory[word_address] = (memory[word_address] & ~mask) | (value << (lane * 8))
    return memory


def load_memory(memory_size, filename="program.elf"):
    """Load all PT_LOAD segments; ``memory_size`` is retained for callers."""
    return _load_segments(filename)


def load_data_memory(memory_size, filename="program.elf"):
    """The data bus sees the same ELF image on a separate simulation port."""
    return _load_segments(filename)


def get_tohost_address(filename="program.elf"):
    with open(filename, "rb") as source:
        elf = ELFFile(source)
        symtab = elf.get_section_by_name(".symtab")
        if symtab is None:
            raise ValueError("ELF has no symbol table")
        symbol = symtab.get_symbol_by_name("tohost")
        if not symbol:
            raise ValueError("Symbol 'tohost' not found in the ELF file")
        return int(symbol[0]["st_value"])


def get_text_section_addr(filename="program.elf"):
    """Cover all allocated executable sections, including bringup vectors."""
    with open(filename, "rb") as source:
        elf = ELFFile(source)
        sections = [section for section in elf.iter_sections()
                    if section["sh_flags"] & 0x4 and section["sh_flags"] & 0x2
                    and section["sh_size"]]
        if not sections:
            raise ValueError("ELF has no allocated executable section")
        return (min(int(section["sh_addr"]) for section in sections),
                max(int(section["sh_addr"] + section["sh_size"]) for section in sections))
