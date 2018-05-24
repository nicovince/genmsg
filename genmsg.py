#!/usr/bin/env python3
import re
from ruamel import yaml
import argparse
import struct


ctype_to_struct_fmt = dict()
ctype_to_struct_fmt["uint8_t"] = "B"
ctype_to_struct_fmt["int8_t"] = "b"
ctype_to_struct_fmt["uint16_t"] = "H"
ctype_to_struct_fmt["int16_t"] = "h"
ctype_to_struct_fmt["uint32_t"] = "I"
ctype_to_struct_fmt["int32_t"] = "i"
ctype_to_struct_fmt["uint8_t[]"] = "%dB"
ctype_to_struct_fmt["int8_t[]"] = "%db"
ctype_to_struct_fmt["uint16_t[]"] = "%dH"
ctype_to_struct_fmt["int16_t[]"] = "%dh"
ctype_to_struct_fmt["uint32_t[]"] = "%dI"
ctype_to_struct_fmt["int32_t[]"] = "%di"


def ctype_to_pack_format(t):
    """Return struct pack/unpack format from c type"""
    if t in ctype_to_struct_fmt.keys():
        return ctype_to_struct_fmt[t]


def is_ctype(t):
    return t in ctype_to_struct_fmt.keys()


def shift_indent_level(s, indent, level):
    indent_prefix = level*indent*" "
    # indent to requested level
    s = re.sub("(^|\n)(.)", r"\1" + indent_prefix + r"\2", s)
    return s


def snake_to_camel(word):
    return ''.join(x.capitalize() or '_' for x in word.split('_'))


class StructField(object):
    """Field of a structure/message"""
    ctype_range = dict()
    ctype_range["uint8_t"] = [0, 255]
    ctype_range["int8_t"] = [-128, 127]
    ctype_range["uint16_t"] = [0, 2**16-1]
    ctype_range["int16_t"] = [-(2**15), 2**15-1]
    ctype_range["uint32_t"] = [0, 2**32-1]
    ctype_range["int32_t"] = [-(2**31), 2**31-1]

    array_re = re.compile(r"^\w+\[(\d*)\]")

    def __init__(self, name, field_type, desc):
        self.name = name
        self.field_type = field_type
        self.desc = desc
        # Check if field is an array and retrieve length
        match_array = self.array_re.match(self.field_type)
        if match_array is not None:
            array_len = match_array.group(1)
            if array_len.isdecimal():
                # Array with fixed size
                self.array_len = int(array_len)
            elif re.match("\s*", array_len):
                # Array with no size limit, length will be hardcoded later
                self.array_len = -1
            else:
                assert False, "Invalid size \"%s\" for array %s" % (self.name, array_len)
        else:
            self.array_len = None

    def is_array(self):
        return self.array_re.match(self.field_type) is not None

    def get_base_type(self):
        return re.sub("\[\d*\]", "", self.field_type)

    def is_ctype(self):
        return self.get_base_type() in ctype_to_struct_fmt.keys()

    def get_range(self):
        """return tuple with min/max value"""
        if self.is_ctype:
            return self.ctype_range[self.get_base_type()]

    def get_field_len(self):
        if self.is_array() and not(self.array_len > 0):
            return None
        else:
            return struct.calcsize(self.get_field_fmt())

    def get_field_fmt(self):
        """Return format used by struct for the whole field
        This includes leading %d if the field is an array or complex type
        """
        if is_ctype(self.field_type):
            fmt = ctype_to_struct_fmt[self.field_type]
            if not self.is_array():
                out = "%s" % (fmt)
            else:
                if self.array_len > 0:
                    # Size of array has been defined in field definition
                    out = "%d%s" (self.array_len, fmt)
                else:
                    out = "%%d%s" % (fmt)
            out = "%s" % (fmt)
        else:
            # TODO: handle array of complex type
            out = "%ds"
        return out

    def get_fmt(self):
        """Return format used by struct without considering if it is an array"""
        if self.is_ctype():
            # Get root type
            t = self.get_base_type()
            out = ctype_to_struct_fmt[t]
        else:
            out = "s"
        return out

    def get_pack_va(self):
        suffix = ""
        if self.is_array():
            prefix = "*"
        elif not is_ctype(self.field_type):
            prefix = "*"
            suffix = ".get_fields()"
        else:
            prefix = ""
        return "%sself.%s%s" % (prefix, self.name, suffix)


class MessageElt(object):
    """Message object created from dictionary definition"""
    def __init__(self, message):
        self.message = message
        if "id" in message.keys():
            self.id = message["id"]
        else:
            self.id = None
        self.name = message["name"]
        self.desc = message["desc"]

        if "fields" in message.keys():
            fields = message["fields"]
            self.fields = [StructField(f["name"], f["type"], f["desc"]) for f in fields]
        else:
            # empty list when message has no fields
            self.fields = list()

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
                # TODO: compute size of previous elements and remove it from array size
                array_suffix = "[255]"
            if f.is_array() and f.array_len:
                array_suffix = "[%d]" % (f.array_len)

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
        return self.name.upper() + "_ID"

    def get_define_msg_id_def(self):
        out = ""
        if self.id is not None:
            out += "#define %s %d\n" % (self.get_define_msg_name(), self.id)
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
        if self.id is not None:
            out += "%smsg_id = %d\n\n" % (current_level*indent*" ", self.id)

        # methods
        out += self.get_init_py_def(indent=indent, level=level+1)
        out += self.get_repr_py_def(indent=indent, level=level+1)
        out += self.get_str_py_def(indent=indent, level=level+1)
        out += self.get_eq_py_def(indent=indent, level=level+1)
        out += self.get_len_py_def(indent=indent, level=level+1)
        out += self.get_fields_py_def(indent=indent, level=level+1)
        out += self.get_struct_fmt_py_def(indent=indent, level=level+1)
        out += self.get_unpack_struct_fmt_py_def(indent=indent, level=level+1)
        out += self.get_pack_py_def(indent=indent, level=level+1)
        out += self.get_unpack_py_def(indent=indent, level=level+1)
        out += self.get_helper_def(indent=indent, level=level+1)
        out += self.get_rand_py_def(indent=indent, level=level+1)
        out += self.get_autotest_py_def(indent=indent, level=level+1)

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
        out += "%sreturn\n\n" % (indent*' ')

        # indent to requested level
        out = shift_indent_level(out, indent, level)
        return out

    def get_struct_fmt_py_def(self, indent=4, level=0):
        """Return method that dynamically compute struct format"""
        # Current level of indentation
        out = "@staticmethod\n"
        out += "def struct_fmt(data):\n"
        cl = 1
        out += "%sfmt = \"\"\n" % (cl*indent*' ')
        for f in self.fields:
            if not(f.is_array()):
                # Get struct format for common types (int8, int16, uint8, ...)
                field_fmt = ctype_to_pack_format(f.field_type)
                if field_fmt is not None:
                    # Regular type, just paste the format
                    out += "%sfmt += \"%s\"\n" % (indent*' ', field_fmt)
                else:
                    # User defined type, call struct_fmt from user defined type
                    field_fmt = "%s.struct_fmt(data)" % (snake_to_camel(f.field_type))
                    out += "%sfmt += %s\n" % (indent*' ', field_fmt)
            else:
                array_type = f.get_base_type()
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
        array_name = "None"
        for f in self.fields:
            if f.is_array():
                array_name = "self.%s" % (f.name)

        # pack method definition
        out = "def pack(self):\n"
        pack_va = ", ".join([f.get_pack_va() for f in self.fields])
        out += "%sfmt = \"<%%s\" %% (self.struct_fmt(%s))\n" % (indent*" ",
                                                               array_name)
        out += "%sreturn struct.pack(fmt, %s)\n\n" % (indent*" ",
                                                      pack_va)

        # indent to requested level
        out = shift_indent_level(out, indent, level)
        return out

    def get_fields_py_def(self, indent=4, level=0):
        """Return method definition that return tuple of fields"""
        out = "def get_fields(self):\n"
        field_names = [f.name for f in self.fields]
        if len(field_names) > 0:
            out += "%sreturn [self.%s]\n" % (indent*' ', ', self.'.join(field_names))
        else:
            out += "%sreturn []\n" % (indent*' ')
        out += "\n"
        # indent to requested level
        out = shift_indent_level(out, indent, level)
        return out

    def get_repr_py_def(self, indent=4, level=0):
        """return __repr__ method for message"""
        # Field names of message
        field_names = [f.name for f in self.fields]
        out = "def __repr__(self):\n"
        out += "%sreturn \"%s(" % (indent*" ", snake_to_camel(self.name))
        if len(field_names) > 0:
            out += "%s=%%r" % ('=%r, '.join(field_names))
            out += ")\" %% (self.%s)" % (', self.'.join(field_names))
        else:
            out += ")\""
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
            if f.is_array():
                array_name = "self.%s" % f.name
                break

        out += "%sreturn struct.calcsize(self.struct_fmt(%s))\n\n" % (indent*' ',
                                                                      array_name)

        # indent to requested level
        out = shift_indent_level(out, indent, level)
        return out

    def get_eq_py_def(self, indent=4, level=0):
        """Return __eq__ method"""
        out = "def __eq__(self, other):\n"
        out += "%sres = True\n" % (indent*' ')
        for f in self.fields:
            out += "%sres = res and (self.%s == other.%s)\n" % (indent*' ',
                                                                f.name, f.name)
        out += "%sreturn res\n\n" % (indent*' ')

        # indent to requested level
        out = shift_indent_level(out, indent, level)
        return out

    def get_rand_py_def(self, indent=4, level=0):
        """Return method which create a random message"""
        out = "@classmethod\n"
        out += "def rand(cls):\n"
        byte_offset = 0
        for f in self.fields:
            if f.is_ctype():
                if f.is_array() and not(f.array_len > 0):
                    out += "%s%s = random.sample(range(%d, %d), random.randint(0, %d))\n" % (indent*' ',
                                                                                             f.name,
                                                                                             f.get_range()[0],
                                                                                             f.get_range()[1],
                                                                                             256-byte_offset)
                elif f.is_array() and (f.array_len > 0):
                    out += "%s%s = random.sample(range(%d, %d), %d)\n" % (indent*' ',
                                                                          f.name,
                                                                          f.get_range()[0],
                                                                          f.get_range()[1],
                                                                          f.array_len)
                else:
                    out += "%s%s = random.randint(*%s)\n" % (indent*' ',
                                                             f.name,
                                                             f.get_range())


            else:
                out += "%s%s = %s.rand()\n" % (indent*' ',
                                               f.name,
                                               snake_to_camel(f.field_type))

        out += "%sreturn %s(" % (indent*' ', snake_to_camel(self.name))
        for f in self.fields:
            out += "%s=%s, " % (f.name, f.name)

        out += ")\n\n"
        # indent to requested level
        out = shift_indent_level(out, indent, level)
        return out

    def get_autotest_py_def(self, indent=4, level=0):

        """Return method testing the class"""
        out = "@classmethod\n"
        out += "def autotest(cls):\n"
        out += "%sinst1 = cls.rand()\n" % (indent*' ')
        out += "%sprint(inst1.pack())\n" % (indent*' ')
        out += "%sprint(str(inst1))\n" % (indent*' ')
        out += "%sassert(inst1 == inst1.unpack(inst1.pack()))\n" % (indent*' ')

        out += "\n"
        # indent to requested level
        out = shift_indent_level(out, indent, level)
        return out

    def get_unpack_struct_fmt_py_def(self, indent=4, level=0):
        """Return struct format for unpacking of message containing a complex type"""
        out = "@staticmethod\n"
        out += "def get_unpack_struct_fmt(data):\n"
        # Current level of indentation
        cl = 1
        # Initialize empty format
        out += "%sfmt = \"\"\n" % (cl*indent*' ')

        for f in self.fields:
            opt_va_arg = ""
            if f.is_ctype() and f.is_array():
                # For array we need to provide length
                # computed as len(data)/struct.calcsize(fmt)
                opt_va_arg = " %% ((len(data)-struct.calcsize(fmt))/%d)" % (struct.calcsize(f.get_fmt()))
            elif not f.is_ctype() and not f.is_array():
                opt_va_arg = " % (len(data))"
            out += "%sfmt += \"%s\"%s\n" % (cl*indent*' ',
                                           f.get_field_fmt(),
                                           opt_va_arg)
        out += "%sreturn fmt\n" % (cl*indent*' ')

        out += "\n"
        # indent to requested level
        out = shift_indent_level(out, indent, level)
        return out

    def get_unpack_py_def(self, indent=4, level=0):
        """return unpack method which convert byte to message object"""
        # Field names of Message
        field_names = [f.name for f in self.fields]

        out = "@classmethod\n"
        out += "def unpack(cls, data):\n"
        
        if len(self.fields) > 0:
            out += "%smsg_fmt = \"<%%s\" %% (cls.get_unpack_struct_fmt(data))\n" % (indent*' ')
            out += "%s(%s) = " % (indent*' ', ', '.join(field_names))
            out += "struct.unpack(msg_fmt, data)"
            if len(field_names) == 1 and "[]" not in self.fields[0].field_type:
                # message has only one element and it is not an array
                # unpack returns a tuple so we need to get the first element in
                # local var
                out += "[0]"
            out += "\n"

            # Convert bytes of complex type to proper object
            for f in self.fields:
                if f.is_array():
                    out += "%s%s = list(%s)\n" % (indent *' ', f.name, f.name)
                if not f.is_ctype():
                    out += "%s%s = %s.unpack(%s)\n" % (indent*' ', f.name,
                                                       snake_to_camel(f.field_type),
                                                       f.name)

        out += "%sreturn %s(" % (indent*' ', snake_to_camel(self.name))
        for f in field_names:
            out += "%s=%s, " % (f, f)
        out += ")"
        out += "\n\n"

        # indent to requested level
        out = shift_indent_level(out, indent, level)
        return out

    def get_helper_def(self, indent=4, level=0):
        """Return string which display message format to help out user"""
        out = "@classmethod\n"
        out += "def helper(cls):\n"
        out += "%sprint(\"%s fields:\")\n" % (indent*' ', snake_to_camel(self.name))
        for f in self.fields:
            out += "%sprint(\"  %s: %s\")\n" % (indent*' ', f.name, f.field_type)

        out += "\n"
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
        self.process_types_defs()
        self.process_enums_defs()

    def process_messages_defs(self):
        """Read message definitions and build objects accordingly"""
        for m in self.defs["messages"]:
            msg_elt = MessageElt(m)
            self.messages.append(msg_elt)

    def process_types_defs(self):
        """Read types definitions"""
        if "types" not in self.defs.keys():
            return
        for t in self.defs["types"]:
            type_elt = MessageElt(t)
            self.messages.append(type_elt)

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
        s += "import random\n"
        s += "import struct\n\n\n"
        return s

    def get_msg_creator_py_def(self, indent=4, level=0):
        """Return function capable of returning message from id and data"""
        cl = 0
        out = "msg_map = dict()\n"
        for m in self.messages:
            if m.id is None:
                continue
            msg_class_name = snake_to_camel(m.name)
            out += "msg_map[%s.msg_id] = %s\n" % (msg_class_name, msg_class_name)
            out += "msg_map[\"%s\"] = %s\n" % (msg_class_name, msg_class_name)
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

    def get_autotest_py_def(self, indent=4, level=0):
        out = "def autotest():\n"
        for m in self.messages:
            out += "%s%s.autotest()\n" % (indent*' ', snake_to_camel(m.name))
        out += "%s\n" % (indent*' ')

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
                py_fd.write(self.get_autotest_py_def())

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
