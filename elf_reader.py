from elftools.elf.elffile import ELFFile

def load_memory(filename="program.elf"):
    with open(filename, 'rb') as file:
        elffile = ELFFile(file)

        text_section = elffile.get_section_by_name('.text')

        if not text_section:
            raise ValueError("No .text section found in the ELF file.")
        
        data = text_section.data()

        memory = []
        for i in range(0, len(data), 4):
            word = data[i:i+4]
            if len(word) < 4:
                break
            memory.append(int.from_bytes(word, byteorder='little'))

    return memory