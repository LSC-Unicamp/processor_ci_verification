from elftools.elf.elffile import ELFFile

def load_memory(memory_size, filename="program.elf"):
    """
    Load the memory contents from the .text and .data sections of an ELF file.
    Args:
        filename (str): Path to the ELF file.
    Returns:
        list: A list of integers representing the memory contents. Each word is 4 bytes.
    """
    memory = [0x13] * memory_size # nop

    with open(filename, 'rb') as file:
        elffile = ELFFile(file)

        text_section = elffile.get_section_by_name('.text')
        textinit_section = elffile.get_section_by_name('.text.init')

        if not text_section and not textinit_section:
            raise ValueError("No .text nor .text.init section found in the ELF file.")

        text_data = text_section.data() if text_section else textinit_section.data()
        text_start_address = text_section['sh_addr'] if text_section else textinit_section['sh_addr']

        pointer = (text_start_address % memory_size) // 4
        for i in range(0, len(text_data), 4):
            word = text_data[i:i+4]
            if len(word) < 4:
                word = word.ljust(4, b'\x00')
            memory[pointer] = int.from_bytes(word, byteorder='little')
            pointer += 1

        data_section = elffile.get_section_by_name('.data')
        if data_section:
            data_data = data_section.data()
            data_start_address = data_section['sh_addr']
            pointer = (data_start_address % memory_size) // 4
            for i in range(0, len(data_data), 4):
                word = data_data[i:i+4]
                if len(word) < 4:
                    word = word.ljust(4, b'\x00')
                memory[pointer] = int.from_bytes(word, byteorder='little')
                pointer += 1

    return memory

def load_data_memory(memory_size, filename="program.elf"):
    data_memory = [0x13] * memory_size # nop
    with open(filename, 'rb') as file:
        elffile = ELFFile(file)

        data_section = elffile.get_section_by_name('.data')
        if data_section:
            data_data = data_section.data()
            data_start_address = data_section['sh_addr']
            pointer = (data_start_address % memory_size) // 4
            for i in range(0, len(data_data), 4):
                word = data_data[i:i+4]
                if len(word) < 4:
                    word = word.ljust(4, b'\x00')
                data_memory[pointer] = int.from_bytes(word, byteorder='little')
                pointer += 1

    return data_memory

def get_tohost_address(filename="program.elf"):
    """
    Retrieve the address of the 'tohost' symbol from an ELF file.
    Args:
        filename (str): Path to the ELF file.
    Returns:
        int: The address of the 'tohost' symbol.
    """
    with open(filename, 'rb') as file:
        elffile = ELFFile(file)

        symtab = elffile.get_section_by_name('.symtab')
        if not symtab:
            raise ValueError("No symbol table found in the ELF file.")

        tohost_symbol = symtab.get_symbol_by_name('tohost')
        if not tohost_symbol:
            raise ValueError("Symbol 'tohost' not found in the ELF file.")

        tohost_addr = tohost_symbol[0]['st_value']
        return tohost_addr

def get_text_section_addr(filename="program.elf"):
    """
    Get the end address of the .text or .text.init section in the ELF file.
    """
    with open(filename, 'rb') as file:
        elffile = ELFFile(file)

        text_section = elffile.get_section_by_name('.text')
        textinit_section = elffile.get_section_by_name('.text.init')
        if text_section:
            start = text_section['sh_addr']
            end = text_section['sh_addr'] + text_section['sh_size']
        elif textinit_section:
            start = textinit_section['sh_addr']
            end = textinit_section['sh_addr'] + textinit_section['sh_size']

    return start, end