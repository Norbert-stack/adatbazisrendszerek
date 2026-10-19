from rich.console import Console
from rich.table import Table
from rich.syntax import Syntax
from rich.panel import Panel
import struct
import os
import sys

console = Console()

def print_help():
    commands = """
python archive.py create data.bin
python archive.py add data.bin kep.jpg
python archive.py add data.bin jegyzet.txt
python archive.py list data.bin
python archive.py extract data.bin kep.jpg
python archive.py remove data.bin kep.jpg
python archive.py compact data.bin
"""
    syntax = Syntax(commands.strip(), "bash", theme="monokai", background_color="default", word_wrap=False)
    console.print(Panel(syntax, title="[bold cyan]Archive CLI[/bold cyan]", subtitle="[dim]Available commands[/dim]", border_style="cyan", padding=(1, 2)))

def print_success(message):
    console.print(f"[green]✓[/green] {message}")

def print_error(message):
    console.print(f"[red]✗[/red] {message}")

def print_info(message):
    console.print(f"[cyan]ℹ[/cyan] {message}")

class FileHeader:
    size = 10

    def __init__(self, magic: int = 0, version: int = 0, file_count: int = 0, deleted_count: int = 0):
        self.magic = magic
        self.version = version
        self.file_count = file_count
        self.deleted_count = deleted_count

    def read(self, file):
        with open(file, "rb") as reader:
            data = reader.read(self.size)
        if len(data) != self.size:
            raise ValueError("Invalid archive header.")
        self.magic, self.version, self.file_count, self.deleted_count = struct.unpack("<IHHH", data)

    def write(self, file):
        data = struct.pack("<IHHH", self.magic, self.version, self.file_count, self.deleted_count)
        with open(file, "r+b") as writer:
            writer.seek(0)
            writer.write(data)

class FileEntry:
    FIXED_SIZE = 18

    def __init__(self, name_len: int = 0, name: str = "", deleted: bool = False, offset: int = 0, size: int = 0):
        self.name_len = name_len
        self.name = name
        self.deleted = deleted
        self.offset = offset
        self.size = size

    @property
    def serialized_size(self):
        return self.FIXED_SIZE + self.name_len

    def read(self, file, position) -> int:
        with open(file, "rb") as reader:
            reader.seek(position)

            self.name_len = struct.unpack("<B", reader.read(1))[0]
            name_data = reader.read(self.name_len)
            self.name = name_data.decode("utf-8")
            data = reader.read(17)

            if len(data) != 17:
                raise ValueError("Invalid FileEntry.")

            self.deleted, self.offset, self.size = struct.unpack("<?QQ", data)

            return reader.tell()

    def write(self, file, position):
        name_data = self.name.encode("utf-8")
        self.name_len = len(name_data)
        data = struct.pack("<B", self.name_len)

        with open(file, "r+b") as writer:
            writer.seek(position)
            writer.write(data)
            writer.write(name_data)
            writer.write(struct.pack("<?QQ", self.deleted, self.offset, self.size))
            return writer.tell()

class FileData:
    def __init__(self, data: bytes = b""):
        self.data = data

    def read(self, file, position, length):
        with open(file, "rb") as reader:
            reader.seek(position)
            self.data = reader.read(length)

    def write(self, file, position):
        with open(file, "r+b") as writer:
            writer.seek(position)
            writer.write(self.data)
            return writer.tell()

class Archive:
    magic = 0x32873
    version = 1

    def __init__(self, file_name):
        self.file_name = file_name
        if not os.path.exists(file_name):
            raise FileNotFoundError(f"Archive '{file_name}' does not exist.")
        self.header = FileHeader()
        self.header.read(file_name)
        if self.header.magic != self.magic:
            raise ValueError("Invalid archive magic.")
        if self.header.version != self.version:
            raise ValueError(f"Unsupported archive version: {self.header.version}")

    @classmethod
    def create(cls, file_name):
        if os.path.exists(file_name):
            raise FileExistsError(f"Archive '{file_name}' already exists.")

        archive = cls.__new__(cls)
        archive.file_name = file_name
        archive.header = FileHeader(magic=cls.magic, version=cls.version, file_count=0, deleted_count=0)

        with open(file_name, "wb"):
            pass

        archive.header.write(file_name)

        return archive

    def add(self, file_name):
        if not os.path.isfile(file_name):
            raise FileNotFoundError(f"File '{file_name}' does not exist.")

        with open(file_name, "rb") as reader:
            data = reader.read()

        file_data = FileData(data)
        file_size = len(data)
        position = FileHeader.size

        for _ in range(self.header.file_count):
            file_entry = FileEntry()
            data_position = file_entry.read(self.file_name, position)

            if file_entry.deleted and file_size <= file_entry.size:
                file_entry.name = file_name
                file_entry.name_len = len(file_name.encode("utf-8"))
                file_entry.deleted = False
                file_entry.size = file_size
                file_entry.write(self.file_name, position)
                file_data.write(self.file_name, file_entry.offset)
                self.header.deleted_count -= 1
                self.header.write(self.file_name)
                print_success(f"Reused deleted block for '{file_name}'.")

                return

            position = data_position + file_entry.size

        file_entry = FileEntry()
        file_entry.name = file_name
        file_entry.name_len = len(file_name.encode("utf-8"))
        file_entry.deleted = False
        file_entry.size = file_size
        file_entry.offset = position + file_entry.serialized_size

        data_position = file_entry.write(self.file_name, position)
        file_data.write(self.file_name, data_position)
        self.header.file_count += 1
        self.header.write(self.file_name)

        print_success(f"Added '{file_name}'.")

    def extract(self, file_name):
        position = FileHeader.size

        for _ in range(self.header.file_count):
            file_entry = FileEntry()
            data_position = file_entry.read(self.file_name, position)

            if file_entry.name == file_name and not file_entry.deleted:
                data_container = FileData()
                data_container.read(self.file_name, file_entry.offset, file_entry.size)

                with open(file_name, "wb") as writer:
                    writer.write(data_container.data)
                print_success(f"Extracted '{file_name}'.")
                return True
            
            position = data_position + file_entry.size

        return False

    def remove(self, file_name):
        position = FileHeader.size

        for _ in range(self.header.file_count):
            file_entry = FileEntry()
            data_position = file_entry.read(self.file_name, position)

            if file_entry.name == file_name and not file_entry.deleted:
                file_entry.deleted = True
                file_entry.write(self.file_name, position)
                self.header.deleted_count += 1
                self.header.write(self.file_name)
                print_success(f"Removed '{file_name}'.")

                return True

            position = data_position + file_entry.size

        return False

    def get_entries_data(self):
        position = FileHeader.size

        entries_data = {}

        for _ in range(self.header.file_count):
            file_entry = FileEntry()
            data_position = file_entry.read(self.file_name, position)
            if not file_entry.deleted:
                file_data = FileData()
                file_data.read(self.file_name, file_entry.offset, file_entry.size)
                entries_data[file_entry] = file_data

            position = data_position + file_entry.size

        return entries_data

    def list(self):
        entries_data = self.get_entries_data()

        console.print(f"Archive: [bold cyan]{self.file_name}[/bold cyan]")
        console.print(f"Version: [yellow]{self.header.version}[/yellow]")
        console.print(f"Total entries: [yellow]{self.header.file_count}[/yellow]")
        console.print(f"Deleted: [red]{self.header.deleted_count}[/red]")
        console.print(f"Active: [green]{self.header.file_count - self.header.deleted_count}[/green]\n")

        table = Table(show_header=True, header_style="bold white")
        table.add_column("NAME")
        table.add_column("OFFSET", justify="right")
        table.add_column("SIZE", justify="right")

        for file_entry in entries_data:
            table.add_row(file_entry.name, str(file_entry.offset), str(file_entry.size))

        console.print(table)

    def compact(self):
        entries_data = self.get_entries_data()

        new_file_count = self.header.file_count - self.header.deleted_count
        os.remove(self.file_name)

        with open(self.file_name, "wb"):
            pass


        self.header = FileHeader(magic=self.magic, version=self.version, file_count=new_file_count, deleted_count=0)
        self.header.write(self.file_name)
        position = FileHeader.size

        for file_entry, file_data in entries_data.items():
            file_entry.deleted = False
            file_entry.offset = position + file_entry.serialized_size
            data_position = file_entry.write(self.file_name, position)
            file_data.write(self.file_name, data_position)
            position = data_position + file_entry.size

        print_success(f"Archive compacted. {new_file_count} active files.")

def create_command_handler(params):
    if len(params) != 1:
        print_help()
        return

    Archive.create(params[0])

    print_success(f"Created archive '{params[0]}'.")

def add_command_handler(params):
    if len(params) < 2:
        print_help()
        return

    archive = Archive(params[0])

    for file_name in params[1:]:
        try:
            archive.add(file_name)
        except FileNotFoundError as error:
            print_error(str(error))

def list_command_handler(params):
    if len(params) != 1:
        print_help()
        return

    archive = Archive(params[0])
    archive.list()

def extract_command_handler(params):
    if len(params) != 2:
        print_help()
        return

    archive = Archive(params[0])

    if not archive.extract(params[1]):
        print_error(f"'{params[1]}' was not found in archive.")

def remove_command_handler(params):
    if len(params) != 2:
        print_help()
        return

    archive = Archive(params[0])

    if not archive.remove(params[1]):
        print_error(f"'{params[1]}' was not found in archive.")

def compact_command_handler(params):
    if len(params) != 1:
        print_help()
        return

    archive = Archive(params[0])

    archive.compact()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print_help()
        sys.exit(0)

    command = sys.argv[1]
    params = sys.argv[2:]

    commands = {
        "create": create_command_handler,
        "add": add_command_handler,
        "list": list_command_handler,
        "extract": extract_command_handler,
        "remove": remove_command_handler,
        "compact": compact_command_handler
    }

    if command not in commands:
        print_error(f"Unknown command: {command}")
        print_help()
        sys.exit(1)

    try:
        commands[command](params)
    except (FileNotFoundError, FileExistsError, ValueError) as error:
        print_error(str(error))
        sys.exit(1)