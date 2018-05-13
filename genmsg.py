#!/usr/bin/env python3
import re
import json
import argparse

def ctype_to_pack_format(t):
    """Return struct pack/unpack format from c type"""
    if t == "uint8_t":
        return "B"
    elif t == "int8_t":
        return "b"
    elif t == "uint16_t":
        return "H"
    elif t == "int16_t":
        return "h"
    elif t == "uint32_t":
        return "I"
    elif t == "int32_t":
        return "i"

class StructField(object):
    """Field of a structure/message"""
    def __init__(self, name, field_type, desc):
        self.name = name
        self.field_type = field_type
        self.desc = desc

class MessageElt(object):
    """Message object created from json file"""
    def __init__(self, message):
        self.message = message
        self.id = message["id"]
        self.name = message["name"]
        self.desc = message["desc"]

        fields = message["fields"]
        self.fields = [StructField(f["name"], f["type"], f["desc"]) for f in fields]

        self.check_message()

    def get_struct_c_def(self, indent=4, level=0):
        """Return string with C struct declaration properly indented"""
        indent_prefix = level*indent*" "

        out = "/* %s */\n" % (self.desc)
        out += "typedef struct {\n"

        for f in self.fields:
            out += "%s%s %s; /* %s */\n" % (indent*" ", f.field_type, f.name, f.desc)

        out += "} %s_t;" % (self.name)

        out = re.sub("(^|\n)", r"\1" + indent_prefix, out)
        return out

    def get_class_py_def(self, indent=4, level=0):
        """Return string with python class declaration and __init__ method"""
        # Field names of Message
        field_names = [f.name for f in self.fields]
        current_level = 0

        # Class definition
        out = "# %s\n" % self.desc
        out += "class %s(object):\n" % self.name
        current_level = current_level + 1

        # Constructor definition
        out += "%sdef __init__(self, %s):\n" % (current_level*indent*" ",
                                               ', '.join(field_names))
        current_level = current_level + 1
        # assign fields
        for f in field_names:
            out += "%sself.%s = %s\n" % (current_level*indent*" ", f, f)

        out = re.sub("(^|\n)", r"\1" + level*indent*" ", out)
        return out

    def get_pack_py_def(self, indent=4, level=0):
        """Return packing function"""
        # Field names of message
        field_names = [f.name for f in self.fields]
        # struct pack/unpack format
        struct_format = ""
        for f in self.fields:
            struct_format += ctype_to_pack_format(f.field_type)

        # pack method definition
        out = "def pack(self):\n"
        out += "%sreturn struct.pack(\"<%s\", self.%s)" % (level*indent*" ",
                                                          struct_format,
                                                          ', self.'.join(field_names))
        out = re.sub("(^|\n)", r"\1" + level*indent*" ", out)
        return out

    def check_message(self):
        """Verify message has unique field names"""
        # Check names duplicates
        names = [e.name for e in self.fields]
        if len(names) != len(set(names)):
            dups = set([ n for n in names if names.count(n) > 1 ])
            raise ValueError("found %s duplicated in %s" % (''.join(dups), self.name))

class EnumEntry(object):
    """Enum entry"""
    def __init__(self, name, value, desc):
        self.name = name
        self.value = value
        self.desc = desc

class EnumElt(object):
    """Enumeration object created from json file"""
    def __init__(self, enum):
        self.enum = enum
        self.name = enum["name"]
        self.desc = enum["desc"]
        entries = enum["entries"]
        self.entries = [EnumEntry(e["entry"], e["value"], e["desc"]) for e in entries]
        self.check_enum()

    def get_enum_c_def(self, indent=4, level=0):
        """Return string with C enum declaration properly indented"""
        indent_prefix = level*indent*" "
        out = "/* %s */\n" % (self.desc)
        out += "typedef enum %s_e {\n" % (self.name)
        max_enum_val = 0
        for e in self.entries:
            out += "%s%s = %d, /* %s */\n" % (indent*" ", e.name, e.value, e.desc)
            max_enum_val = max(max_enum_val, e.value)
        out += "%s%s_END = %d\n" % (indent*" ", self.name, max_enum_val+1)
        out += "} %s_t;" % (self.name)
        out = re.sub("(^|\n)", r"\1" + indent_prefix, out)
        return out

    def get_enum_py_def(self, indent=4, level=0):
        """Return string with python enum declaration properly indented"""
        indent_prefix = level*indent*" "
        out = "# %s\n" % (self.desc)
        out += "class %s(Enum):\n" % (self.name)
        max_enum_val = 0
        for e in self.entries:
            out += "%s%s = %d # %s\n" % (indent*" ", e.name, e.value, e.desc)
            max_enum_val = max(max_enum_val, e.value)
        out = re.sub("(^|\n)", r"\1" + indent_prefix, out)
        return out

    def check_enum(self):
        """Verify enum has only one instance of each name and value"""
        # Check names duplicates
        names = [e.name for e in self.entries]
        if len(names) != len(set(names)):
            dups = set([ n for n in names if names.count(n) > 1 ])
            raise ValueError("found %s duplicated in %s" % (''.join(dups), self.name))
        # Check values duplicates
        vals = [e.value for e in self.entries]
        if len(vals) != len(set(vals)):
            dups = set([ str(n) for n in vals if vals.count(n) > 1 ])
            raise ValueError("found value %s used for more than one name in %s" % (' '.join(dups), self.name))

class DefsGen(object):
    def __init__(self, defs, indent, out_dir):
        self.defs = defs
        self.indent = indent
        self.out_dir = out_dir
        self.messages = list()
        self.enums = list()

    def process_messages_defs(self):
        for m in self.defs["messages"]:
            msg_elt = MessageElt(m)
            print(msg_elt.get_struct_c_def(4))
            print()
            print(msg_elt.get_class_py_def())
            print()
            print(msg_elt.get_pack_py_def(4,1))

    def process_enums_defs(self):
        for e in self.defs["enums"]:
            enum_elt = EnumElt(e)
            print(enum_elt.get_enum_c_def(3,1))
            print(enum_elt.get_enum_py_def(3,1))


def main():
    parser = argparse.ArgumentParser(description="Process json message and enum definition to generate C structure or python serializing/deserializing",
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("json_file", type=str,
                        help="Json file containing messages definitions")
    parser.add_argument("--indent", type=int, default=4,
                        help="number of spaces per indentation")
    args = parser.parse_args()

    msg_file = open(args.json_file)
    messages = json.load(msg_file)

    defs_gen = DefsGen(messages, args.indent, ".")
    defs_gen.process_messages_defs()
    defs_gen.process_enums_defs()


if __name__ == "__main__":
    main()
