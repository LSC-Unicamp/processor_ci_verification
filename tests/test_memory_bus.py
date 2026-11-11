import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from memory_bus import read_bus_words, write_bus_words


def test_wide_store_and_load_share_all_word_lanes():
    memory = [0] * 64
    data = sum((lane + 1) << (lane * 32) for lane in range(8))
    writes = write_bus_words(memory, 16, data, (1 << 32) - 1, 256)
    assert writes == [(lane * 4, lane + 1) for lane in range(8)]
    assert read_bus_words(memory, 16, 256) == data
    assert read_bus_words(memory, 23, 32) == 8


def test_byte_enables_preserve_unselected_bytes_and_words():
    memory = [0xaaaaaaaa] * 16
    writes = write_bus_words(memory, 2, 0x12345678, 0b0101, 256)
    assert writes == [(0, 0xaa34aa78)]
    assert memory[3:10] == [0xaaaaaaaa] * 7
    assert read_bus_words(memory, 2, 32) == 0xaa34aa78
