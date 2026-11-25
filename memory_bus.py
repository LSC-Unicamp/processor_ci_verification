"""Word-addressed memory operations for wrapper data buses."""


def _index(memory, word):
    # Small list fixtures retain their historical circular addressing. Real
    # ELF memories are sparse mappings keyed by the full physical word address.
    return word % len(memory) if isinstance(memory, list) else word


def write_masked_word(memory, index, data, byte_enable):
    """Apply a four-byte mask; return the written word or None."""
    if not 0 <= byte_enable <= 0b1111:
        raise ValueError(f"Invalid byte enable: {byte_enable}")
    if byte_enable == 0:
        return None
    mask = sum(0xff << (8 * lane) for lane in range(4) if byte_enable & (1 << lane))
    word = (memory[index] & ~mask) | (data & mask)
    memory[index] = word
    return word


def read_bus_words(memory, index, width, byte_offset=0):
    if width < 32 or width % 32:
        raise ValueError(f"Invalid data bus width: {width}")
    value = sum(
        memory[_index(memory, index + lane)] << (32 * lane)
        for lane in range(width // 32)
    )
    return value >> (8 * byte_offset)


def write_bus_words(memory, index, data, byte_enable, width):
    """Return (byte offset, written word) for every selected 32-bit lane."""
    if width < 32 or width % 32:
        raise ValueError(f"Invalid data bus width: {width}")
    if byte_enable < 0 or byte_enable >= 1 << (width // 8):
        raise ValueError(f"Invalid byte enable: {byte_enable}")
    writes = []
    for lane in range(width // 32):
        word = write_masked_word(
            memory,
            _index(memory, index + lane),
            (data >> (lane * 32)) & 0xffffffff,
            (byte_enable >> (lane * 4)) & 0xf,
        )
        if word is not None:
            writes.append((lane * 4, word))
    return writes
