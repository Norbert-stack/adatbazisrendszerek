
'''
A készített hasítótábla struktúra hatránya, hogy amikor a betelnek a slotok akkor 
újra fel kell építeni a táblát amely elég időigényes, ezért lenne, jobb egy olyan megoldás
ahol lenne egy fix meghatározott számú bucketünk amiben B-fa vagy B+ fa csomópontot implementálunk 
'''
import struct
import hashlib

class DynamicHashTable:
    HEADER = struct.Struct("!QII")
    # Q = 8 bájtos unsigned integer (hash)
    # I = 4 bájtos unsigned integer (kulcs hossza)
    # I = 4 bájtos unsigned integer (érték hossza)

    HASH_FUNCTIONS = [
        hashlib.sha256,
        hashlib.blake2b,
        hashlib.sha3_256,
        hashlib.md5,
    ]

    def __init__(self, capacity=8, max_load=0.7):
        capacity = max(8, capacity)
        self.capacity = 1 << (capacity - 1).bit_length()

        self.max_load = max_load
        self.size = 0
        self.hash_id = 0
        self.slots = [None] * self.capacity

    def _hash(self, key, function_id):
        data = key.encode("utf-8")
        algorithm = self.HASH_FUNCTIONS[function_id]
        digest = algorithm(data).digest()

        return int.from_bytes(digest[:8], "big")

    def _indices(self, key):
        h1 = self._hash(key, self.hash_id)

        second_id = (self.hash_id + 1) % len(self.HASH_FUNCTIONS)
        h2 = self._hash(key, second_id)

        index = h1 & (self.capacity - 1)

        step = (h2 & (self.capacity - 1)) | 1

        return index, step

    def _encode(self, key, value):
        key_bytes = key.encode("utf-8")
        value_bytes = value.encode("utf-8")

        h = self._hash(key, self.hash_id)

        header = self.HEADER.pack(
            h,
            len(key_bytes),
            len(value_bytes),
        )

        return header + key_bytes + value_bytes

    def _decode(self, record):
        h, key_len, value_len = self.HEADER.unpack_from(record)

        start = self.HEADER.size
        key_bytes = record[start:start + key_len]
        value_bytes = record[
            start + key_len:start + key_len + value_len
        ]

        key = key_bytes.decode("utf-8")
        value = value_bytes.decode("utf-8")

        return h, key, value

    def _find_slot(self, key):
        index, step = self._indices(key)

        for _ in range(self.capacity):
            record = self.slots[index]

            if record is None:
                return index, False

            _, stored_key, _ = self._decode(record)

            if stored_key == key:
                return index, True

            index = (index + step) & (self.capacity - 1)

        return None, False

    def __setitem__(self, key, value):
        if not isinstance(key, str) or not isinstance(value, str):
            raise TypeError("A kulcs és az érték is szöveg legyen.")

        index, found = self._find_slot(key)

        if found:
            self.slots[index] = self._encode(key, value)
            return

        if index is None or (
            self.size + 1
        ) / self.capacity > self.max_load:
            self._resize()
            index, found = self._find_slot(key)

        self.slots[index] = self._encode(key, value)
        self.size += 1

    def __getitem__(self, key):
        index, found = self._find_slot(key)

        if not found:
            raise KeyError(key)

        _, _, value = self._decode(self.slots[index])
        return value

    def __contains__(self, key):
        _, found = self._find_slot(key)
        return found

    def _resize(self):
        old_slots = self.slots

        self.capacity *= 2

        self.hash_id = (
            self.hash_id + 1
        ) % len(self.HASH_FUNCTIONS)

        self.slots = [None] * self.capacity
        self.size = 0

        for record in old_slots:
            if record is not None:
                _, key, value = self._decode(record)
                self[key] = value

    def __len__(self):
        return self.size

    def __repr__(self):
        items = []

        for record in self.slots:
            if record is not None:
                _, key, value = self._decode(record)
                items.append(f"{key!r}: {value!r}")

        return (
            f"DynamicHashTable("
            f"capacity={self.capacity}, "
            f"size={self.size}, "
            f"hash_id={self.hash_id}, "
            f"items={{{', '.join(items)}}})"
        )

# Itt tesztelem
if __name__ == "__main__":
    table = DynamicHashTable(capacity=4)
    
    table["nev"] = "Norbi"
    table["nyelv"] = "Python"
    table["projekt"] = "Hash tábla"
    
    print(table["nev"])
    print(table["nyelv"])
    print("projekt" in table)
    print("Elemszám:", len(table))
    print(table)

    for i in range(100):
        table[f"kulcs_{i}"] = f"ertek_{i}"

    print("Új kapacitás:", table.capacity)
    print("Összes elem:", len(table))
    print("Ellenőrzés:", table["kulcs_42"])

    print(table)

    
