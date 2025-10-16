from elftools.elf.elffile import ELFFile

def load_memory(filename="program.elf"):
    """
    Load the memory contents from the .text section of an ELF file.
    Args:
        filename (str): Path to the ELF file.
    Returns:
        list: A list of integers representing the memory contents. Each word is 4 bytes.
    """
    with open(filename, 'rb') as file:
        elffile = ELFFile(file)

        text_section = elffile.get_section_by_name('.text')
        textinit_section = elffile.get_section_by_name('.text.init')

        if not text_section and not textinit_section:
            raise ValueError("No .text nor .text.init section found in the ELF file.")
        
        data = text_section.data() if text_section else textinit_section.data()

        memory = []
        for i in range(0, len(data), 4):
            word = data[i:i+4]
            if len(word) < 4:
                break
            memory.append(int.from_bytes(word, byteorder='little'))

    return memory

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