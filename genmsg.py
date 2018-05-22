#!/usr/bin/env python3
import re
from ruamel import yaml
import argparse
import struct


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


def shift_indent_level(s, indent, level):
    indent_prefix = level*indent*" "
    # indent to requested level
    s = re.sub("(^|\n)(.)", r"\1" + indent_prefix + r"\2", s)
    return s


def snake_to_camel(word):
    return ''.join(x.capitalize() or '_' for x in word.split('_'))


class StructField(object):
    """Field of a structure/message"""
    def __init__(self, name, field_type, desc):
        self.name = name
        self.field_type = field_type
        self.desc = desc

    def get_pack_va(self):
        if "[]" not in self.field_type:
            prefix = ""
        else:
            prefix = "*"
        return "%sself.%s" % (prefix, self.name)


class MessageElt(object):
    """Message object created from dictionary definition"""
    def __init__(self, message):
        self.message = message
        self.id = message["id"]
        self.name = message["name"]
        self.desc = message["desc"]

        fields = message["fields"]
        self.fields = [StructField(f["name"], f["type"], f["desc"]) for f in fields]

        self.check_message()

    def get_struct_c_def(self, indent=4, level=0):
        """Return string with C struct declaration of messages"""
        indent_prefix = level*indent*" "

        out = "/* %s */\n" % (self.desc)
        out += "#pragma pack(push, 1)\n"
        out += "typedef struct {\n"

        for f in self.fields:
            array_suffix = ""
            if "[]" in f.field_type:
                array_suffix = "[255]"
            out += "%s%s %s%s; /* %s */\n" % (indent*" ",
                                              f.field_type.replace("[]", ""),
                                              f.name, array_suffix, f.desc)

        out += "} %s_t;\n" % (self.name)
        out += "#pragma pack(pop)\n"

        out += "\n"
        # indent to requested level
        out = shift_indent_level(out, indent, level)
        return out

    def get_define_msg_name(self):
        return self.name.upper()

    def get_define_msg_id_def(self):
        out = "#define %s %d\n" % (self.get_define_msg_name(), self.id)
        return out

    def get_struct_py_fmt(self):
        """return struct format"""
        # Field names of message
        field_names = [f.name for f in self.fields]
        return "<" + ''.join([ctype_to_pack_format(f.field_type) for f in self.fields])

    def get_class_py_def(self, indent=4, level=0):
        """Return string with python class declaration"""
        current_level = 0

        # Class definition
        out = "# %s\n" % self.desc
        out += "class %s(object):\n" % snake_to_camel(self.name)
        current_level = current_level + 1
        out += "%smsg_id = %d\n\n" % (current_level*indent*" ", self.id)

        # methods
        out += self.get_init_py_def(indent=indent, level=level+1)
        out += self.get_repr_py_def(indent=indent, level=level+1)
        out += self.get_str_py_def(indent=indent, level=level+1)
        out += self.get_len_py_def(indent=indent, level=level+1)
        out += self.get_struct_fmt_py_def(indent=indent, level=level+1)
        out += self.get_pack_py_def(indent=indent, level=level+1)
        out += self.get_unpack_py_def(indent=indent, level=level+1)

        out += "\n"
        # indent to requested level
        out = shift_indent_level(out, indent, level)
        return out

    def get_init_py_def(self, indent=4, level=0):
        """Return constructor method"""
        # Field names of Message
        field_names = [f.name for f in self.fields]

        out = "def __init__(self, %s):\n" % (', '.join(field_names))
        # assign fields
        for f in field_names:
            out += "%sself.%s = %s\n" % (indent*' ', f, f)
        out += "\n"

        # indent to requested level
        out = shift_indent_level(out, indent, level)
        return out

    def get_struct_fmt_py_def(self, indent=4, level=0):
        """Return method that dynamically compute struct format"""
        # Current level of indentation
        out = "@staticmethod\n"
        out += "def struct_fmt(data):\n"
        cl = 1
        out += "%sfmt = \"<\"\n" % (cl*indent*' ')
        for f in self.fields:
            if "[]" not in f.field_type:
                field_fmt = ctype_to_pack_format(f.field_type)
                out += "%sfmt += \"%s\"\n" % (indent*' ', field_fmt)
            else:
                array_type = f.field_type.replace("[]", "")
                field_fmt = ctype_to_pack_format(array_type)
                out += "%sif type(data) == bytes:\n" % (cl*indent*' ')
                cl += 1
                out += "%sn_elt = len(data) / struct.calcsize(\"%s\")\n" % (cl*indent*' ',
                                                                            field_fmt)
                cl -= 1
                out += "%selse:\n" % (cl*indent*' ')
                cl += 1
                out += "%sn_elt = len(data)\n" % (cl*indent*' ')
                cl -= 1
                out += "%sfmt += \"%%d%s\" %% (n_elt - struct.calcsize(fmt))\n" % (cl*indent*' ', field_fmt)
        out += "%sreturn fmt\n\n" % (indent*' ')

        # indent to requested level
        out = shift_indent_level(out, indent, level)
        return out

    def get_pack_py_def(self, indent=4, level=0):
        """Return packing function"""
        # Field names of message
        field_names = [f.name for f in self.fields]
        struct_pack_va = ""
        array_name = "None"
        for f in self.fields:
            if "[]" not in f.field_type:
                struct_pack_va += "self.%s," % (f.name)
            else:
                struct_pack_va += "*self.%s," % (f.name)
                array_name = "self.%s" % (f.name)

        # pack method definition
        out = "def pack(self):\n"
        pack_va = ", ".join([f.get_pack_va() for f in self.fields])
        out += "%sreturn struct.pack(self.struct_fmt(%s), %s)\n\n" % (indent*" ",
                                                                      array_name,
                                                                      pack_va)

        # indent to requested level
        out = shift_indent_level(out, indent, level)
        return out

    def get_repr_py_def(self, indent=4, level=0):
        """return __repr__ method for message"""
        # Field names of message
        field_names = [f.name for f in self.fields]
        out = "def __repr__(self):\n"
        out += "%sreturn \"%s(" % (indent*" ", snake_to_camel(self.name))
        out += "%s=%%r" % ('=%r, '.join(field_names))
        out += ")\" %% (self.%s" % (', self.'.join(field_names))
        out += ")"
        out += "\n\n"

        # indent to requested level
        out = shift_indent_level(out, indent, level)
        return out

    def get_str_py_def(self, indent=4, level=0):
        """return __str__ method for message"""
        # Field names of message
        field_names = [f.name for f in self.fields]
        out = "def __str__(self):\n"
        out += "%sout = \"\"\n" % (indent*' ')
        for f in field_names:
            out += "%sout += \"%s: %%s\\n\" %% (str(self.%s))\n" % (indent*' ',
                                                                    f, f)
        out += "%sreturn out\n\n" % (indent*' ')

        # indent to requested level
        out = shift_indent_level(out, indent, level)
        return out

    def get_len_py_def(self, indent=4, level=0):
        """Return method capable of counting message object length"""
        out = "def __len__(self):\n"
        array_name = "None"
        for f in self.fields:
            if "[]" in f.field_type:
                array_name = "self.%s" % f.name
                break

        out += "%sreturn struct.calcsize(self.struct_fmt(%s))\n\n" % (indent*' ',
                                                                      array_name)

        # indent to requested level
        out = shift_indent_level(out, indent, level)
        return out

    def get_unpack_py_def(self, indent=4, level=0):
        """return unpack method which"""
        # Field names of Message
        field_names = [f.name for f in self.fields]

        out = "@classmethod\n"
        out += "def unpack(cls, data):\n"
        out += "%smsg_fmt = cls.struct_fmt(data)\n" % (indent*' ')
        out += "%s(%s) = " % (indent*' ', ', '.join(field_names))
        out += "struct.unpack(msg_fmt, data)"

        if len(field_names) == 1 and "[]" not in self.fields[0].field_type:
            # message has only one element and it is not an array
            # unpack returns a tuple so we need to get the first element in
            # local var
            out += "[0]"
        out += "\n"
        out += "%sreturn %s(" % (indent*' ', snake_to_camel(self.name))
        for f in field_names:
            out += "%s=%s, " % (f, f)
        out += ")"
        out += "\n\n"

        # indent to requested level
        out = shift_indent_level(out, indent, level)
        return out

    def check_message(self):
        """Verify message has unique field names"""
        # Check names duplicates
        names = [e.name for e in self.fields]
        if len(names) != len(set(names)):
            dups = set([n for n in names if names.count(n) > 1])
            raise ValueError("found %s duplicated in %s"
                             % (''.join(dups), self.name))


class EnumEntry(object):
    """Enum entry"""
    def __init__(self, name, value, desc):
        self.name = name
        self.value = value
        self.desc = desc


class EnumElt(object):
    """Enumeration object created from dictionary definition"""
    def __init__(self, enum):
        self.enum = enum
        self.name = enum["name"]
        self.desc = enum["desc"]
        entries = enum["entries"]
        self.entries = [EnumEntry(e["entry"], e["value"], e["desc"]) for e in entries]
        self.check_enum()

    def get_enum_c_def(self, indent=4, level=0):
        """Return string with C enum declaration"""
        indent_prefix = level*indent*" "
        out = "/* %s */\n" % (self.desc)
        out += "typedef enum %s_e {\n" % (self.name)
        max_enum_val = 0
        for e in self.entries:
            out += "%s%s = %d, /* %s */\n" % (indent*" ",
                                              e.name, e.value, e.desc)
            max_enum_val = max(max_enum_val, e.value)
        out += "%s%s_END = %d\n" % (indent*" ", self.name, max_enum_val+1)
        out += "} %s_t;\n\n" % (self.name)

        # indent to requested level
        out = shift_indent_level(out, indent, level)
        return out

    def get_enum_py_def(self, indent=4, level=0):
        """Return string with python enum declaration"""
        indent_prefix = level*indent*" "
        out = "# %s\n" % (self.desc)
        out += "class %s(Enum):\n" % (self.name)
        max_enum_val = 0
        for e in self.entries:
            out += "%s%s = %d  # %s\n" % (indent*" ", e.name, e.value, e.desc)
            max_enum_val = max(max_enum_val, e.value)
        out += "%s%s_MAX = %d\n\n" % (indent*" ", self.name.upper(),
                                      max_enum_val+1)

        # indent to requested level
        out = shift_indent_level(out, indent, level)
        return out

    def check_enum(self):
        """Verify enum has only one instance of each name and value"""
        # Check names duplicates
        names = [e.name for e in self.entries]
        if len(names) != len(set(names)):
            dups = set([n for n in names if names.count(n) > 1])
            raise ValueError("found %s duplicated in %s"
                             % (''.join(dups), self.name))
        # Check values duplicates
        vals = [e.value for e in self.entries]
        if len(vals) != len(set(vals)):
            dups = set([str(n) for n in vals if vals.count(n) > 1])
            raise ValueError("found value %s used for more than one name in %s"
                             % (' '.join(dups), self.name))


class DefsGen(object):
    def __init__(self, defs, indent, h_gen, h_dest, py_gen, py_dest):
        self.defs = defs
        self.indent = indent
        self.h_gen = h_gen
        self.h_dest = h_dest
        self.py_gen = py_gen
        self.py_dest = py_dest
        self.filename_prefix = "messages"

        self.messages = list()
        self.enums = list()

        self.process_messages_defs()
        self.process_enums_defs()

    def process_messages_defs(self):
        """Read message definitions and build objects accordingly"""
        for m in self.defs["messages"]:
            msg_elt = MessageElt(m)
            self.messages.append(msg_elt)

    def process_enums_defs(self):
        """Read enums definitions and build objects accordingly"""
        if "enums" not in self.defs.keys():
            return
        for e in self.defs["enums"]:
            enum_elt = EnumElt(e)
            self.enums.append(enum_elt)

    def get_h_header(self):
        define = "__" + self.filename_prefix.upper() + "_H__"
        s = "#ifndef %s\n" % define
        s += "#define %s\n\n" % define
        return s

    def get_h_footer(self):
        define = "__" + self.filename_prefix.upper() + "_H__"
        s = "#endif // %s\n" % define
        return s

    def get_py_header(self):
        s = "#!/usr/bin/env python3\n"
        s += "from enum import Enum\n"
        s += "import struct\n\n\n"
        return s

    def get_msg_creator_py_def(self, indent=4, level=0):
        """Return function capable of returning message from id and data"""
        cl = 0
        out = "msg_map = dict()\n"
        for m in self.messages:
            out += "msg_map[%d] = %s\n" % (m.id, snake_to_camel(m.name))
        out += "\n\n"
        out += "def msg_creator(msg_id, msg_len, data):\n"
        cl += 1
        indent_prefix = cl*indent*' '
        out += "%sif msg_id in msg_map.keys():\n" % (indent_prefix)
        cl += 1
        indent_prefix = cl*indent*' '
        out += "%sreturn msg_map[msg_id].unpack(data)\n" % (indent_prefix)
        cl -= 1
        indent_prefix = cl*indent*' '
        out += "%selse:\n" % (indent_prefix)
        cl += 1
        indent_prefix = cl*indent*' '
        out += "%sreturn data\n\n" % (indent_prefix)

        # indent to requested level
        out = shift_indent_level(out, indent, level)
        return out

    def process_defs(self):
        if self.h_gen:
            h_file = self.h_dest + "/" + self.filename_prefix + ".h"
            with open(h_file, 'w') as h_fd:
                h_fd.write(self.get_h_header())

                # Write Messages C definitions
                for m in self.messages:
                    h_fd.write(m.get_define_msg_id_def())
                    h_fd.write(m.get_struct_c_def())

                # Write Enums C definitions
                for e in self.enums:
                    h_fd.write(e.get_enum_c_def())
                h_fd.write(self.get_h_footer())

        if self.py_gen:
            py_file = self.py_dest + "/" + self.filename_prefix + ".py"
            with open(py_file, 'w') as py_fd:
                py_fd.write(self.get_py_header())

                # Write Messages python definitions
                for m in self.messages:
                    py_fd.write(m.get_class_py_def())

                # Write Enums python definitions
                for e in self.enums:
                    py_fd.write(e.get_enum_py_def())

                py_fd.write(self.get_msg_creator_py_def())

                py_fd.write("# End of file\n")


def main():
    parser = argparse.ArgumentParser(description="Process yaml message and enum definition to generate C structure or python serializing/deserializing",
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("yaml_file", type=str,
                        help="Yaml file containing messages definitions")
    parser.add_argument("--indent", type=int, default=4,
                        help="number of spaces per indentation")
    parser.add_argument("--h-gen", action='store_true', default=False,
                        help="Enable generation of c header files containing struct and enums")
    parser.add_argument("--h-dest", type=str, default="./",
                        help="destination folder for header files")
    parser.add_argument("--py-gen", action='store_true', default=False,
                        help="Enable generation of python files containing struct and enums")
    parser.add_argument("--py-dest", type=str, default="./",
                        help="destination folder for python files")
    args = parser.parse_args()

    msg_file = open(args.yaml_file)
    messages = yaml.safe_load(msg_file)

    defs_gen = DefsGen(messages, args.indent,
                       args.h_gen, args.h_dest,
                       args.py_gen, args.py_dest)
    defs_gen.process_defs()


if __name__ == "__main__":
    main()
