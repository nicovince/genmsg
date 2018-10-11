#!/usr/bin/env python3
import re
from ruamel import yaml
import argparse
import struct
import math


def shift_indent_level(s, indent, level):
    indent_prefix = level*indent*" "
    # indent to requested level
    s = re.sub("(^|\n)(.)", r"\1" + indent_prefix + r"\2", s)
    return s

def snake_to_camel(word):
    return ''.join(x.capitalize() or '_' for x in word.split('_'))

class Bits(object):
    """Bits description within a bitfield

    Describe one or more bit in a bitfield with a name, position, width, description.
    An enumeration can be attached to a bits description
    """
    def __init__(self, name, position, desc, prefix, width=1):
        """Bits initializer

        name: string describing the bit(s)
        position: index within the bitfield of the LSB of the bit(s),
        desc: string giving a description of what the bit(s) do
        """
        self.name = name
        self.position = position
        self.desc = desc
        self.width = width
        self.prefix = prefix
        self.enum = None

    def __str__(self):
        if self.width == 1:
            return "%s[%d]" % (self.name, self.position)
        else:
            return "%s[%d-%d]" % (self.name, self.upper_bit_pos(), self.position)

    def __repr__(self):
        return "%s(name=%r, position=%r, desc=%r, prefix=%r, width=%r)" % (self.__class__.__name__,
                                                                           self.name,
                                                                           self.position,
                                                                           self.desc,
                                                                           self.prefix,
                                                                           self.width)

    def __eq__(self, other):
        """Test if two bits are equals"""
        return ((self.name == other.name) and (self.position == other.position)
                and (self.desc == other.desc) and (self.width == other.width)
                and (self.prefix == other.prefix))

    def __lt__(self, other):
        """Test bit order based on position in the field"""
        return self.position < other.position

    def get_str_range(self):
        """Return string range for this bit(s)"""
        if self.width == 1:
            return "%d" % self.position
        else:
            return "%d:%d" % (self.upper_bit_pos(), self.position)

    def attach_enum(self, name):
        self.enum = name

    def upper_bit_pos(self):
        """Return upper bit position"""
        return self.position + self.width - 1

    def bit_conflicts(self, other):
        """Return true when two bits conflicts

        Two bits can conflict if position overlaps
        Do not conflict with itself
        """
        if self == other:
            return False
        if ((self.upper_bit_pos() < other.position)
            or (self.position > other.upper_bit_pos())):
            return False

        return True

    def get_bits_name(self):
        return self.prefix.upper() + "_" + self.name.upper()

    def get_bits_mask(self):
        """Mask of the bits, not shifted to position"""
        return (1 << self.width) -1

    def get_bits_c_def(self, indent=4, level=0):
        """Return string with C define for bits description"""
        cl = 0

        out = "/* %s */\n" % (self.desc)
        # Bits position and mask if width > 1
        if self.width == 1:
            out += "#define %s (1 << %d)\n" % (self.get_bits_name(), self.position)
        else:
            out += "#define %s_MASK (0x%x << %d)\n" % (self.get_bits_name(),
                                                       self.get_bits_mask(),
                                                       self.position)
            out += "#define %s_POS %d\n" % (self.get_bits_name(), self.position)

        # Enums shifted to bits position
        if self.enum is not None:
            enum_def = DefsGen.instance.get_enum(self.enum)
            for e in enum_def.entries:
                enum_prefix = self.get_bits_name()
                out += "#define %s_%s (%s << %s_POS)\n" % (enum_prefix,
                                                           e.get_enum_name(),
                                                           e.get_enum_name(),
                                                           self.get_bits_name())

        out += "\n"
        # indent to requested level
        out = shift_indent_level(out, indent, level)
        return out

    def get_class_name(self):
        suffix = "_bit"
        if self.width > 1:
            suffix += "s"
        return snake_to_camel(self.name + suffix)

    def get_init_py_def(self, indent=4, level=0):
        """Return class initializer"""
        cl = 0
        out = "%sdef __init__(self, value):\n" % (cl*indent*' ')
        cl += 1
        out += "%sself.value = value\n" % (cl*indent*' ')

        out += "\n"
        # indent to requested level
        out = shift_indent_level(out, indent, level)
        return out

    def get_str_py_def(self, indent=4, level=0):
        """Return __str__ method for Bit"""
        cl = 0
        out = "def __str__(self):\n"
        cl += 1
        out += "%sreturn \"%s: %%s\" %% (self._value)\n" % (cl*indent*' ',
                                                           self.name)
        out += "\n"
        # indent to requested level
        out = shift_indent_level(out, indent, level)
        return out

    def get_repr_py_def(self, indent=4, level=0):
        """Return __repr__ method for Bit"""
        cl = 0
        out = "def __repr__(self):\n"
        cl += 1
        out += "%sreturn  \"%s(" % (cl*indent*' ', self.get_class_name())
        out += "value=%s)\" % (str(self.value))\n"
        out += "\n"
        # indent to requested level
        out = shift_indent_level(out, indent, level)
        return out

    def get_getter_py_def(self, indent=4, level=0):
        """Return getter definition"""
        cl = 0
        out = "%s@property\n" % (cl*indent*' ')
        out += "%sdef value(self):\n" % (cl*indent*' ')
        cl += 1
        out += "%sreturn self._value\n" % (cl*indent*' ')

        out += "\n"
        # indent to requested level
        out = shift_indent_level(out, indent, level)
        return out

    def get_setter_py_def(self, indent=4, level=0):
        """Return setter definition"""
        cl = 0
        out = "%s@value.setter\n" % (cl*indent*' ')
        out += "%sdef value(self, value):\n" % (cl*indent*' ')
        cl += 1
        # verify value is within range
        if self.enum is None:
            if self.width == 1:
                out += "%sassert (value == 0) or (value == 1), " % (cl*indent*' ')
                out += "\"Invalid value %%d for bit %s\" %% (value)\n" % (self.name)
            else:
                out += "%sassert ((value | 0x%x) >> %d) == 0, " % (cl*indent*' ',
                                                                   self.get_bits_mask(),
                                                                   self.width)
                out += "\"Invalid value %%d for bit %s\" %% (value)\n" % (self.name)
        else:
            enum_def = DefsGen.instance.get_enum(self.enum)
            out += "%sassert value.__class__.__name__ == \"%s\", " % (cl*indent*' ',
                                                                      enum_def.get_class_name())
            out += "\"Invalid value %%r for bit %s, must be of kind %s\" %% (value)\n" % (self.name,
                                                                                          enum_def.get_class_name())

        out += "%sself._value = value\n" % (cl*indent*' ')

        out += "\n"
        # indent to requested level
        out = shift_indent_level(out, indent, level)
        return out

    def get_pack_py_def(self, indent=4, level=0):
        """Return bit packing function"""
        cl = 0
        out = "def pack(self):\n"
        cl += 1
        if self.enum is None:
            out += "%sreturn self._value << %d\n" % (cl*indent*' ', self.position)
        else:
            out += "%sreturn self._value.value << %d\n" % (cl*indent*' ', self.position)

        out += "\n"
        # indent to requested level
        out = shift_indent_level(out, indent, level)
        return out

    def get_class_py_def(self, indent=4, level=0):
        """Return Bit Class Definition"""
        cl = 0
        out = "\n%sclass %s(object):\n" % (cl*indent*' ', self.get_class_name())
        cl += 1
        out += "%s\"\"\"%s\"\"\"\n" % (cl*indent*' ', self.desc)
        out += "%sposition = %d\n" % (cl*indent*' ', self.position)
        out += "%swidth = %d\n" % (cl*indent*' ', self.width)
        out += "%sname = \"%s\"\n" % (cl*indent*' ', self.name)
        out += self.get_init_py_def(indent, cl)
        out += self.get_str_py_def(indent, cl)
        out += self.get_repr_py_def(indent, cl)
        out += self.get_pack_py_def(indent, cl)
        out += self.get_getter_py_def(indent, cl)
        out += self.get_setter_py_def(indent, cl)

        # indent to requested level
        out = shift_indent_level(out, indent, level)
        return out


class BitField(object):
    """Bit field description

    Describe bits within a field with a name position width and description
    """

    def __init__(self, bitfield, name=None):
        """BitField initializer

        bitfield: dictionary from element yaml 'bitfields' list or 'bitfield'
                  entry in fields dictionary
        name: Required if bitfield is attached to 'bitfields' list and not to a
              particular field
        """
        self.bitfield = bitfield
        self.name = name
        self.bits = list()
        if "name" in self.bitfield.keys():
            self.name = self.bitfield["name"]
        # Check we have a name, descriptions and bits
        assert self.name is not None, "bitfield is missing name"
        assert "desc" in self.bitfield.keys(), "bitfield %s is missing description" % (self.name)
        assert "bits" in self.bitfield.keys(), "bitfield is missing bits description"
        self.desc = self.bitfield["desc"]

        for b in self.bitfield["bits"]:
            # Check bit fields have name, position and description
            assert "name" in b.keys(), "bit is missing name"
            assert "position" in b.keys(), "bit %s is missing position" % (b["name"])
            assert "desc" in b.keys(), "bit %s is missing description" % (b["name"])
            width = 1
            if "width" in b.keys():
                width = b["width"]
            # Create bit
            bit = Bits(b["name"], b["position"], b["desc"], self.name, width)

            if "enum" in b:
                enum_name = b["enum"]
                bit.attach_enum(enum_name)
                # Override bit width from enum required width
                enum_def = DefsGen.instance.get_enum(enum_name)
                assert enum_def is not None, "Enum %s must be defined before using it in bitfield %s" % (enum_name, self.name)
                bit.width = enum_def.get_enum_bit_width()

            # Check bit does not conflicts with each others
            for other_bit in self.bits:
                assert not bit.bit_conflicts(other_bit), "Bit position in %s conflicts between %s and %s" % (self.name, bit.name, other_bit.name)

            self.bits.append(bit)

    def __str__(self):
        out = "%s:\n" % (self.name)
        # Work on copy of bits because sort works 'in place'
        bits = self.bits
        # Display bits msb first
        bits.sort()
        bits.reverse()
        for b in bits:
            out += "%s  [%s] %s\n" % (len(self.name)*' ', b.get_str_range(), b.name)
        return out[:-1]

    def get_bitwidth(self):
        """Return bitwidth used by this bitfield"""
        max_bit = 0
        for b in self.bits:
            max_bit = max(max_bit, b.upper_bit_pos())
        return max_bit + 1

    def get_base_type(self):
        """Return matching ctype"""
        bitwidth = self.get_bitwidth()
        assert bitwidth <= 32, "Bitwidth for bitfield %s must not exceed 32 bits" % (self.name)
        if bitwidth <= 8:
            return "uint8_t"
        elif bitwidth <= 16:
            return "uint16_t"
        elif bitwidth <= 32:
            return "uint32_t"

    def get_bitfield_c_defines(self, indent=4, level=0):
        """Return string containing defines for bitfield"""
        out = ""
        if self.name is not None:
            out += "/* %s bitfield */\n" % (self.name)

        for bit in self.bits:
            out += bit.get_bits_c_def(indent, level)

        out += "\n"
        # indent to requested level
        out = shift_indent_level(out, indent, level)
        return out

    def get_class_name(self):
        return snake_to_camel(self.name + "_bit_field")

    def get_init_py_def(self, indent=4, level=0):
        """Return BitField Initializer"""
        cl = 0
        bits = list(self.bits)
        bits.sort()
        bits_names = [b.name for b in bits]
        out = "%sdef __init__(self, %s):\n" % (cl*indent*' ', ', '.join(bits_names))
        cl += 1
        for b in bits:
            out += "%sself._%s = self.%s(%s)\n" % (cl*indent*' ', b.name,
                                                   b.get_class_name(), b.name)

        out += "\n"
        # indent to requested level
        out = shift_indent_level(out, indent, level)
        return out

    def get_str_py_def(self, indent=4, level=0):
        """Return __str__ method for BitField"""
        cl = 0
        out = "def __str__(self):\n"
        cl += 1
        out += "%sout = \"\"\n" % (cl*indent*' ')
        bits = list(self.bits)
        bits.sort()
        bits.reverse()
        for b in bits:
            out += "%sout += \"%%s\\n\" %% (self._%s)\n" % (cl*indent*' ',
                                                            b.name)
        out += "%sreturn out\n" % (cl*indent*' ')
        out += "\n"
        # indent to requested level
        out = shift_indent_level(out, indent, level)
        return out

    def get_pack_py_def(self, indent=4, level=0):
        """Return function which packs all bitfields"""
        cl = 0
        out = "def pack(self):\n"
        cl += 1
        out += "%s\"\"\"Pack each bit of bitfield and return packed integer.\"\"\"\n" % (cl*indent*' ')
        out += "%sret = 0\n" % (cl*indent*' ')
        bits = list(self.bits)
        bits.sort()
        bits.reverse()
        for b in bits:
            out += "%sret |= self.%s.pack()\n" % (cl*indent*' ', b.name)

        out += "%sreturn ret\n" % (cl*indent*' ')

        out += "\n"
        # indent to requested level
        out = shift_indent_level(out, indent, level)
        return out

    def get_getters_py_def(self, indent=4, level=0):
        """Return getters for each bit of the bitfield"""
        cl = 0
        out = ""
        for b in self.bits:
            out += "%s@property\n" % (cl*indent*' ')
            out += "%sdef %s(self):\n" % (cl*indent*' ', b.name)
            cl += 1
            out += "%sreturn self._%s\n\n" % (cl*indent*' ', b.name)
            cl -= 1

        # indent to requested level
        out = shift_indent_level(out, indent, level)
        return out

    def get_setters_py_def(self, indent=4, level=0):
        """Return setters for each bit of the bitfield"""
        cl = 0
        out = ""
        for b in self.bits:
            out += "%s@%s.setter\n" % (cl*indent*' ', b.name)
            out += "%sdef %s(self, value):\n" % (cl*indent*' ', b.name)
            cl += 1
            out += "%sself._%s.value = value\n\n" % (cl*indent*' ', b.name)
            cl -= 1

        # indent to requested level
        out = shift_indent_level(out, indent, level)
        return out

    def get_class_py_def(self, indent=4, level=0):
        """Return string with python class declaration for BitField"""
        cl = 0
        out = "%sclass %s(object):\n" % (cl*indent*' ', self.get_class_name())
        cl += 1
        out += "%s\"\"\"%s\"\"\"\n" % (cl*indent*' ', self.desc)
        # define class for each bit(s) definition
        for b in self.bits:
            out += b.get_class_py_def(indent, cl)

        out += self.get_init_py_def(indent, cl)
        out += self.get_getters_py_def(indent, cl)
        out += self.get_setters_py_def(indent, cl)
        out += self.get_str_py_def(indent, cl)
        out += self.get_pack_py_def(indent, cl)

        out += "\n"
        # indent to requested level
        out = shift_indent_level(out, indent, level)
        return out


class StructField(object):
    """Field of a structure/message"""
    ctype_range = dict()
    ctype_range["uint8_t"] = [0, 255]
    ctype_range["int8_t"] = [-128, 127]
    ctype_range["uint16_t"] = [0, 2**16-1]
    ctype_range["int16_t"] = [-(2**15), 2**15-1]
    ctype_range["uint32_t"] = [0, 2**32-1]
    ctype_range["int32_t"] = [-(2**31), 2**31-1]

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

    array_re = re.compile(r"^\w+\[(\d*)\]")

    def __init__(self, name, field_type, desc):
        self.name = name
        self.field_type = field_type
        self.desc = desc
        self.enum = None
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

    def attach_enum(self, name):
        self.enum = name

    def is_array(self):
        return self.array_re.match(self.field_type) is not None

    def get_base_type(self):
        """Return Base type for the field

        Either a struct or ctype, for bitfields, the matching ctype is returned
        """
        bf = DefsGen.instance.get_bitfield(self.field_type)
        if bf is not None:
            return bf.get_base_type()
        return re.sub("\[\d*\]", "", self.field_type)

    def is_bitfield(self):
        bf = DefsGen.instance.get_bitfield(self.field_type)
        return bf is not None

    def is_ctype(self):
        if self.is_bitfield() is not None:
            return True
        else:
            return self.get_base_type() in self.ctype_to_struct_fmt.keys()

    def get_range(self):
        """return tuple with min/max value"""
        if self.is_ctype:
            return self.ctype_range[self.get_base_type()]

    def get_field_len(self):
        if self.is_array() and not(self.array_len > 0):
            return None
        else:
            return struct.calcsize(self.get_field_fmt())

    def get_class_name(self):
        if not(self.is_ctype()):
            return snake_to_camel(self.get_base_type())

    def get_field_fmt(self):
        """Return format used by struct for the whole field
        This includes leading %d if the field is an array or complex type
        """
        if self.is_ctype():
            fmt = self.ctype_to_struct_fmt[self.get_base_type()]
            if not self.is_array():
                out = "%s" % (fmt)
            else:
                if self.array_len > 0:
                    # Size of array has been defined in field definition
                    out = "%d%s" % (self.array_len, fmt)
                else:
                    out = "%%d%s" % (fmt)
        else:
            out = "%ds"
        return out

    def get_fmt(self):
        """Return format used by struct without considering if it is an array"""
        if self.is_ctype():
            # Get root type
            t = self.get_base_type()
            out = self.ctype_to_struct_fmt[t]
        else:
            out = "s"
        return out

    def get_pack_va(self):
        suffix = ""
        if self.is_ctype():
            if self.is_array():
                prefix = "*"
            else:
                prefix = ""
        else:
            if not(self.is_array()):
                prefix = "*"
                suffix = ".get_fields()"
            else:
                return "*[e.get_fields() for e in self.%s]" % (self.name)
        return "%sself.%s%s" % (prefix, self.name, suffix)

    def get_argparse_decl(self, parser_name, indent=4, level=0):
        """Return insctruction to register option to parser"""
        help_str = "help='%s'" % self.desc
        out = ""
        if self.is_ctype():
            if self.enum is None:
                choices = ""
                metavar = ""
                default = "default=0, "
                argtype = "type=int, "
            else:
                choices = "choices=[f(x) for x in %s for f in (lambda x: x, lambda x: x.value)], " % (snake_to_camel(self.enum))
                metavar = "metavar=[f(x) for x in %s for f in (lambda x: x.name.lower(), lambda x: x.value)], " % (snake_to_camel(self.enum))
                default = "default=list(%s)[0].value, " % (snake_to_camel(self.enum))
                argtype = "type=%s.%s_type, " % (snake_to_camel(self.enum), self.enum)
                out += "enum_help = list()\n"
                out += "for e in [e.value for e in %s]:\n" % (snake_to_camel(self.enum))
                out += "%senum_help.append(\"%%d: %%s\" %% (e, %s(e).name.lower()))\n" % (indent*' ', snake_to_camel(self.enum))

                help_str = "help='%s (%%s)' %% (' - '.join(enum_help))" % (self.desc)
            # nargs
            if self.is_array():
                if self.array_len > 0:
                    nargs = "nargs=%d, " % self.array_len
                else:
                    nargs = "nargs='+', "
            else:
                nargs = ""
            out += "%s.add_argument('--%s', %s%s%s%s%s%s)\n" % (parser_name,
                                                                self.name,
                                                                argtype,
                                                                nargs,
                                                                choices,
                                                                metavar,
                                                                default,
                                                                help_str)
        else:
            # TODO Fix default
            default = [0xA, 0xB]
            out += "%s.add_argument('--%s', nargs='*', default=%s, %s)\n" % (parser_name,
                                                                             self.name,
                                                                             default,
                                                                             help_str)
        # indent to requested level
        out = shift_indent_level(out, indent, level)
        return out


class MessageElt(object):
    """Message object created from dictionary definition"""
    def __init__(self, message):
        self.message = message
        if "id" in message.keys():
            self.id = message["id"]
        else:
            self.id = None

        assert "name" in message.keys(), "message is missing name"
        assert "desc" in message.keys(), "message %s is missing desc" % (message["name"])
        self.name = message["name"]
        self.desc = message["desc"]

        self.fields = list()
        if "fields" in message.keys():
            fields = message["fields"]
            for f in fields:
                assert "name" in f.keys(), "Field of %s is missing name" % self.name
                assert "type" in f.keys(), "Field %s of %s is missing type" % (f["name"],
                                                                               self.name)
                assert "desc" in f.keys(), "Field %s of %s is missing desc" % (f["name"],
                                                                               self.name)
                struct_field = StructField(f["name"], f["type"], f["desc"])
                if "enum" in f:
                    struct_field.attach_enum(f["enum"])
                self.fields.append(struct_field)

        self.check_message()

    def get_class_name(self):
        return snake_to_camel(self.name)

    def get_struct_c_def(self, indent=4, level=0):
        """Return string with C struct declaration of messages"""
        indent_prefix = level*indent*" "

        out = "/* %s */\n" % (self.desc)
        if len(self.fields) > 0:
            out += "#pragma pack(push, 1)\n"
            out += "typedef struct {\n"

            for f in self.fields:
                array_suffix = ""
                if f.is_ctype():
                    type_str = f.get_base_type()
                else:
                    type_str = "%s_t" % (f.get_base_type())
                if f.is_array():
                    if not(f.array_len > 0):
                        # TODO: compute size of previous elements and remove it from array size
                        array_suffix = "[255]"
                    else:
                        array_suffix = "[%d]" % (f.array_len)

                out += "%s%s %s%s; /* %s */\n" % (indent*" ",
                                                  type_str,
                                                  f.name, array_suffix, f.desc)

            out += "} %s_t;\n" % (self.name)
            out += "#pragma pack(pop)\n"
        else:
            out += "/* No Fields for this message */\n"

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

    def get_class_py_def(self, indent=4, level=0):
        """Return string with python class declaration"""
        current_level = 0

        # Class definition
        out = "class %s(object):\n" % snake_to_camel(self.name)
        current_level = current_level + 1
        out += "%s\"\"\"%s\"\"\"\n" % (current_level*indent*' ', self.desc)
        out += "%sn_fields = %d\n\n" % (current_level*indent*" ", len(self.fields))
        if self.id is not None:
            out += "%smsg_id = %d\n\n" % (current_level*indent*" ", self.id)

        # methods
        out += self.get_init_py_def(indent=indent, level=level+1)
        out += self.get_repr_py_def(indent=indent, level=level+1)
        out += self.get_str_py_def(indent=indent, level=level+1)
        out += self.get_eq_py_def(indent=indent, level=level+1)
        out += self.get_len_py_def(indent=indent, level=level+1)
        out += self.get_n_fields_py_def(indent=indent, level=level+1)
        out += self.get_fields_py_def(indent=indent, level=level+1)
        out += self.get_struct_fmt_py_def(indent=indent, level=level+1)
        out += self.get_unpack_struct_fmt_py_def(indent=indent, level=level+1)
        out += self.get_pack_py_def(indent=indent, level=level+1)
        out += self.get_unpack_py_def(indent=indent, level=level+1)
        out += self.get_helper_def(indent=indent, level=level+1)
        out += self.get_rand_py_def(indent=indent, level=level+1)
        out += self.get_autotest_py_def(indent=indent, level=level+1)
        out += self.get_argparse_group_py_def(indent=indent, level=level+1)
        out += self.get_args_handler(indent=indent, level=level+1)

        out += "\n"
        # indent to requested level
        out = shift_indent_level(out, indent, level)
        return out

    def get_init_py_def(self, indent=4, level=0):
        """Return initializer method"""
        # Field names of Message
        field_names = [f.name for f in self.fields]

        out = "def __init__(self, %s):\n" % (', '.join(field_names))
        cl = 1
        # assign fields
        for f in self.fields:
            if f.enum is not None and not(f.is_array()):
                out += "%sassert %s in %s, \"Invalid value for %s (%%s)\" %% (%s)\n" % (cl*indent*' ',
                                                                                        f.name,
                                                                                        snake_to_camel(f.enum),
                                                                                        f.name,
                                                                                        f.name)
            elif f.enum is not None and f.is_array():
                out += "%sfor v in %s:\n" % (cl*indent*' ', f.name)
                cl += 1
                out += "%sassert v in %s, \"Invalid value for %s (%%s)\" %% (%s)\n" % (cl*indent*' ',
                                                                                       snake_to_camel(f.enum),
                                                                                       f.name, f.name)
                cl -= 1
            out += "%sself.%s = %s\n" % (cl*indent*' ', f.name, f.name)
        out += "%sreturn\n\n" % (cl*indent*' ')

        # indent to requested level
        out = shift_indent_level(out, indent, level)
        return out

    def get_n_fields_py_def(self, indent=4, level=0):
        """Return method that compute number of fields in message
        This includes number of fields in complex type fields
        """
        out = "@classmethod\n"
        out += "def get_n_fields(cls):\n"
        cl = 1
        out += "%sn = 0\n" % (cl*indent*' ')
        out += "%ssuffix = ''\n" % (cl*indent*' ')
        for f in self.fields:
            if f.is_ctype():
                if not(f.is_array()):
                    out += "%sn += 1 # %s\n" % (cl*indent*' ',
                                                f.name)
                else:
                    if f.array_len > 0:
                        out += "%sn += %d # %s\n" % (cl*indent*' ',
                                                     f.array_len,
                                                     f.name)
                    else:
                        out += "%ssuffix = '+' # %s\n" % (cl*indent*' ',
                                                          f.name)
                        out += "%sn += 1 # %s\n" % (cl*indent*' ',
                                                    f.name)
            else:
                out += "%s(%s_n, %s_suffix) = %s.get_n_fields()\n" % (cl*indent*' ',
                                                                      f.name,
                                                                      f.name,
                                                                      f.get_class_name())
                out += "%sn += %s_n\n" % (cl*indent*' ', f.name)
                out += "%ssuffix = %s_suffix\n" % (cl*indent*' ', f.name)

        out += "%sreturn (n, suffix)\n" % (cl*indent*' ')
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
        out += "%sfmt = \"\"\n" % (cl*indent*' ')
        for f in self.fields:
            if f.is_ctype():
                if not(f.is_array()) or (f.array_len > 0):
                    out += "%sfmt += \"%s\"\n" % (cl*indent*' ', f.get_field_fmt())
                else:
                    out += "%sfmt += \"%s\" %% (len(data))\n" % (cl*indent*' ',
                                                                 f.get_field_fmt())
            else:
                # Complex type
                if not(f.is_array()):
                    out += "%sfmt += %s.struct_fmt(data)\n" % (cl*indent*' ',
                                                               f.get_class_name())
                elif f.is_array() and f.array_len > 0:
                    out += "%sfor e in range(%d):\n" % (cl*indent*' ', f.array_len)
                    cl += 1

                    out += "%sfmt += %s.struct_fmt(data)\n" % (cl*indent*' ',
                                                               f.get_class_name())
                    cl -= 1
                else:
                    out += "%sfor e in range(len(data)):\n" % (cl*indent*' ')
                    cl += 1

                    out += "%sfmt += %s.struct_fmt(data)\n" % (cl*indent*' ',
                                                               f.get_class_name())
                    cl -= 1

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
        cl = 1
        pack_va = ", ".join([f.get_pack_va() for f in self.fields])
        out += "%sva_args = list()\n" % (cl*indent*' ')
        for f in self.fields:
            if f.is_ctype():
                enum_suffix = ""
                if f.enum is not None:
                    enum_suffix = ".value"
                if not(f.is_array()):
                    out += "%sva_args.append(self.%s%s)\n" % (cl*indent*' ', f.name,
                                                              enum_suffix)
                else:
                    out += "%sva_args.extend([e%s for e in self.%s])\n" % (cl*indent*' ',
                                                                           enum_suffix,
                                                                           f.name)
            else:
                if not(f.is_array()):
                    out += "%sva_args.extend(self.%s.get_fields())\n" % (cl*indent*' ',
                                                                         f.name)
                else:
                    out += "%sfor e in self.%s:\n" % (cl*indent*' ', f.name)
                    cl += 1
                    out += "%sva_args.extend(e.get_fields())\n" % (cl*indent*' ')
                    cl -= 1

        out += "%sfmt = \"<%%s\" %% (self.struct_fmt(%s))\n" % (cl*indent*" ",
                                                                array_name)
        out += "%sreturn struct.pack(fmt, *va_args)\n\n" % (cl*indent*" ")

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
        out = "def __str__(self):\n"
        out += "%sout = \"%s:\\n\"\n" % (indent*' ', self.name)
        for f in self.fields:
            if f.enum is None:
                out += "%sout += \"  %s: %%s\\n\" %% (str(self.%s))\n" % (indent*' ',
                                                                          f.name, f.name)
            else:
                if not(f.is_array()):
                    out += "%sout += \"  %s: %%s\\n\" %% (%s(self.%s).name)\n" % (indent*' ',
                                                                                  f.name,
                                                                                  snake_to_camel(f.enum),
                                                                                  f.name)
                else:
                    out += "%sl = [%s(v).name for v in self.%s]\n" % (indent*' ',
                                                                      snake_to_camel(f.enum),
                                                                      f.name)
                    out += "%sout += \"  %s: %%s\\n\" %% (l)\n" % (indent*' ', f.name)
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

        out += "%sreturn struct.calcsize('<%%s' %% self.struct_fmt(%s))\n\n" % (indent*' ',
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
                if f.enum is None:
                    population_str = "range(%d, %d)" % (f.get_range()[0], f.get_range()[1])
                else:
                    population_str = "list(%s)" % (snake_to_camel(f.enum))
                if f.is_array() and not(f.array_len > 0):
                    out += "%s%s = [random.choice(%s) for e in range(random.randint(0, %d))]\n" % (indent*' ',
                                                                                                   f.name,
                                                                                                   population_str,
                                                                                                   256-byte_offset)
                elif f.is_array() and (f.array_len > 0):
                    out += "%s%s = [random.choice(%s) for e in range(%d)]\n" % (indent*' ',
                                                                                f.name,
                                                                                population_str,
                                                                                f.array_len)
                else:
                    if f.enum is None:
                        out += "%s%s = random.randint(*%s)\n" % (indent*' ',
                                                                 f.name,
                                                                 f.get_range())
                    else:
                        out += "%s%s = random.choice(%s)\n" % (indent*' ',
                                                               f.name,
                                                               population_str)

            else:
                if f.is_array():
                    if f.array_len > 0:
                        n = f.array_len
                        out += "%s%s = [%s.rand() for e in range(%d)]\n" % (indent*' ',
                                                                            f.name,
                                                                            snake_to_camel(f.get_base_type()),
                                                                            n)
                    else:
                        # TODO: use space left instead of 255
                        out += "%sn = random.randint(1, int(255/struct.calcsize(%s.struct_fmt(None))))\n" % (indent*' ',
                                                                                                             f.get_class_name())
                        out += "%s%s = [%s.rand() for e in range(int(n))]\n" % (indent*' ',
                                                                                f.name,
                                                                                f.get_class_name())
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

    def get_args_handler(self, indent=4, level=0):
        """Return method which process args and return object"""
        out = "@classmethod\n"
        out += "def args_handler(cls, args):\n"
        args = ""
        for f in self.fields:
            if len(args) > 0:
                args += ", "
            args += "%s=args.%s" % (f.name, f.name)

        out += "%sreturn %s(%s)\n" % (indent*' ', self.get_class_name(), args)
        out += "\n"
        # indent to requested level
        out = shift_indent_level(out, indent, level)
        return out

    def get_argparse_group_py_def(self, indent=4, level=0):
        """Return method adding option group to subparser for current message"""
        out = "@classmethod\n"
        out += "def get_argparse_group(cls, subparser):\n"
        parser_name = "parser_%s" % (self.name)
        formatter_class_str = "formatter_class=argparse.ArgumentDefaultsHelpFormatter"
        out += "%s%s = subparser.add_parser('%s', %s, help='%s')\n" % (indent*' ',
                                                                       parser_name,
                                                                       self.name,
                                                                       formatter_class_str,
                                                                       self.desc)
        for f in self.fields:
            if f.is_ctype():
                out += "%s" % (f.get_argparse_decl(parser_name, indent=indent, level=1))
            else:
                out += self.get_argparse_decl(parser_name, f, indent=indent, level=1)
        out += "%s%s.set_defaults(func=%s.args_handler)\n" % (indent*' ',
                                                              parser_name,
                                                              self.get_class_name())
        out += "\n"
        # indent to requested level
        out = shift_indent_level(out, indent, level)
        return out

    def get_argparse_decl(self, parser_name, field, indent=4, level=0):
        """Return instruction to register option to parser
        The fields are given as raw data"""
        out = "(nargs, suffix) = %s.get_n_fields()\n" % (field.get_class_name())
        out += "%s.add_argument('--%s', type=int, nargs=nargs)" % (parser_name, field.name,)
        out += "\n"
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
        out = "@staticmethod\n"
        out += "def get_unpack_struct_fmt(data):\n"
        # Current level of indentation
        cl = 1
        # Initialize empty format
        out += "%sfmt = \"\"\n" % (cl*indent*' ')
        for f in self.fields:
            if f.is_ctype():
                if not(f.is_array()) or f.array_len > 0:
                    out += "%sfmt += \"%s\"\n" % (cl*indent*' ', f.get_field_fmt())
                else:
                    # Unknown array size
                    # field format contains %d which needs to be computed at
                    # runtime
                    out += "%sif type(data) == bytes:\n" % (cl*indent*' ')
                    cl += 1
                    out += "%sfmt += \"%s\" %% ((len(data) - struct.calcsize(fmt))/%s)\n" % (cl*indent*' ',
                                                                                             f.get_field_fmt(),
                                                                                             struct.calcsize(f.get_fmt()))
                    cl -= 1
                    out += "%selse:\n" % (cl*indent*' ')
                    cl += 1
                    out += "%sfmt += \"%s\" %% (len(data))\n" % (cl*indent*' ',
                                                                 f.get_field_fmt())
                    cl -= 1
            else:
                # Complex type
                if not(f.is_array()):
                    out += "%soffset = struct.calcsize(fmt)\n" % (cl*indent*' ')
                    arg = "struct.calcsize(%s.get_unpack_struct_fmt(data[offset:]))" % (f.get_class_name())
                    out += "%sfmt += \"%s\" %% (%s)\n" % (cl*indent*' ',
                                                          f.get_field_fmt(),
                                                          arg)
                else:
                    # Array of complex type
                    if f.array_len > 0:
                        # Fixed size
                        out += "%sfor e in range(%d):\n" % (cl*indent*' ', f.array_len)
                        cl += 1
                        arg = "struct.calcsize(%s.get_unpack_struct_fmt(None))" % (f.get_class_name())
                        out += "%sfmt += \"%s\" %% (%s)\n" % (cl*indent*' ',
                                                              f.get_field_fmt(),
                                                              arg)
                        cl -= 1
                    else:
                        # variable size
                        out += "%sheader_sz = struct.calcsize('<%%s' %% (fmt))\n" % (cl*indent*' ')
                        out += "%sarray_sz = len(data) - header_sz\n" % (cl*indent*' ')
                        out += "%selt_sz = struct.calcsize(%s.struct_fmt(None))\n" % (cl*indent*' ', f.get_class_name())
                        out += "%sfor e in range(int(array_sz/elt_sz)):\n" % (cl*indent*' ')
                        cl += 1
                        out += "%sfmt += '%%ds' %% (elt_sz)\n" % (cl*indent*' ')
                        cl -= 1

        out += "%sreturn fmt\n\n" % (cl*indent*' ')
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
            out += "%sunpacked = struct.unpack(msg_fmt, data)\n" % (indent*' ')

            # Assign each field from raw unpacked
            offset = 0
            for f in self.fields:
                if not(f.is_array()):
                    if f.is_ctype():
                        if f.enum is None:
                            out += "%s%s = unpacked[%d]\n" % (indent*' ', f.name, offset)
                        else:
                            out += "%s%s = %s(unpacked[%d])\n" % (indent*' ', f.name,
                                                                  snake_to_camel(f.enum),
                                                                  offset)
                        offset += 1
                    else:
                        out += "%s%s = unpacked[%d]\n" % (indent*' ', f.name, offset)
                        offset += 1
                else:
                    if f.is_ctype():
                        if (f.array_len > 0):
                            # Array size is known in advance,
                            # retrieve exact number of elements
                            out += "%s%s = unpacked[%d:%d]\n" % (indent*' ', f.name,
                                                                 offset,
                                                                 offset + f.array_len)
                            offset += f.array_len
                        else:
                            # Array size is known at runtime only
                            # Such arrays *must* be at the end of the message definition,
                            # therefore we know there is nothing after.
                            out += "%s%s = unpacked[%d:]\n" % (indent*' ', f.name, offset)
                        if f.enum is not None:
                            out += "%s%s = [%s(e) for e in %s]\n" % (indent*' ', f.name,
                                                                     snake_to_camel(f.enum),
                                                                     f.name)
                    else:
                        # Complex type
                        if f.array_len > 0:
                            out += "%s%s = unpacked[%d:%d]\n" % (indent*' ', f.name,
                                                                 offset,
                                                                 offset + f.array_len)
                            offset += f.array_len
                        else:
                            # Array size is known at runtime only
                            # Such arrays *must* be at the end of the message definition,
                            # therefore we know there is nothing after.
                            out += "%s%s = unpacked[%d:]\n" % (indent*' ', f.name, offset)

            # Convert bytes of complex type to proper object
            for f in self.fields:
                if f.is_array():
                    out += "%s%s = list(%s)\n" % (indent*' ', f.name, f.name)
                if not f.is_ctype():
                    if not(f.is_array()):
                        out += "%s%s = %s.unpack(%s)\n" % (indent*' ', f.name,
                                                           f.get_class_name(),
                                                           f.name)
                    else:
                        out += "%s%s = [%s.unpack(e) for e in %s]\n" % (indent*" ",
                                                                        f.name,
                                                                        f.get_class_name(),
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

    def __lt__(self, other):
        return self.value < other.value

    def get_enum_name(self):
        """Return enum name to use in generated files"""
        return self.name.upper()


class EnumElt(object):
    """Enumeration object created from dictionary definition"""
    def __init__(self, enum):
        self.enum = enum
        assert "name" in enum.keys(), "Enum is missing name"
        assert "desc" in enum.keys(), "Enum %s is missing desc" % (enum["name"])
        assert "entries" in enum.keys(), "Enum %s is missing entries" % (enum["name"])
        self.name = enum["name"]
        self.desc = enum["desc"]
        entries = enum["entries"]
        self.entries = list()
        for e in entries:
            assert "entry" in e.keys(), "Enum %s is missing entry name" % (self.name)
            assert "desc" in e.keys(), "Enum %s entry %s is missing desc" % (self.name,
                                                                             e["entry"])
            assert "value" in e.keys(), "Enum %s entry %s is missing entry value" % (self.name,
                                                                                     e["name"])
            self.entries.append(EnumEntry(e["entry"], e["value"], e["desc"]))
        self.check_enum()

    def get_enum_bit_width(self):
        """Return number of bits needed to code maximum value present in enum"""
        max_val = 0
        for entry in self.entries:
            max_val = max(max_val, entry.value)
        return math.ceil(math.log(max_val + 1, 2))

    def get_enum_c_def(self, indent=4, level=0):
        """Return string with C enum declaration"""
        out = "/* %s */\n" % (self.desc)
        out += "typedef enum %s_e {\n" % (self.name)
        max_enum_val = 0
        for e in self.entries:
            out += "%s%s = %d, /* %s */\n" % (indent*" ",
                                              e.get_enum_name(), e.value, e.desc)
            max_enum_val = max(max_enum_val, e.value)
        out += "%s%s_END = %d\n" % (indent*" ", self.name, max_enum_val+1)
        out += "} %s_t;\n\n" % (self.name)

        # indent to requested level
        out = shift_indent_level(out, indent, level)
        return out

    def get_enum_py_def(self, indent=4, level=0):
        """Return string with python enum declaration"""
        out = "# %s\n" % (self.desc)
        out += "class %s(Enum):\n" % (snake_to_camel(self.name))
        for e in self.entries:
            out += "%s%s = %d  # %s\n" % (indent*" ", e.get_enum_name(), e.value, e.desc)

        out += "\n"
        out += self.get_enum_eq_py_def(indent=indent, level=level+1)
        out += self.get_enum_type_py_def(indent=indent, level=level+1)
        out += self.get_enum_hash_py_def(indent=indent, level=level+1)
        out += self.get_enum_default_py_def(indent=indent, level=level+1)

        # indent to requested level
        out = shift_indent_level(out, indent, level)
        return out

    def get_class_name(self):
        return snake_to_camel(self.name)

    def get_enum_eq_py_def(self, indent=4, level=0):
        """Return function which compares enum"""
        cl = 0
        out = "def __eq__(self, other):\n"
        cl += 1
        out += "%s# This is required because enum imported from different location fails equality tests\n" % (cl*indent*' ')
        out += "%s# First test the two object have the same class name\n" % (cl*indent*' ')
        out += "%sif other.__class__.__name__ == self.__class__.__name__:\n" % (cl*indent*' ')
        cl += 1
        out += "%s# Then check values\n" % (cl*indent*' ')
        out += "%sreturn self.value == other.value\n" % (cl*indent*' ')
        cl -= 1
        out += "%selse:\n" % (cl*indent*' ')
        cl += 1
        out += "%sreturn False\n" % (cl*indent*' ')
        out += "\n"
        # indent to requested level
        out = shift_indent_level(out, indent, level)
        return out

    def get_enum_type_py_def(self, indent=4, level=0):
        """Generate function used for 'type' parameter during argparse declaration"""
        cl = 0
        out = "def %s_type(s):\n" % (self.name)
        cl += 1
        out += "%s\"\"\"Return Enum object from string representation\n\n" % (cl*indent*' ')
        out += "%sUsed in type parameter of argparse declaration\"\"\"\n" % (cl*indent*' ')
        out += "%stry:\n" % (cl*indent*' ')
        cl += 1
        out += "%sif s.isdecimal():\n" % (cl*indent*' ')
        # arg is decimal
        cl += 1
        out += "%sreturn %s(int(s))\n" % (cl*indent*' ', self.get_class_name())
        cl -= 1
        out += "%selse:\n" % (cl*indent*' ')
        # Arg is enum string
        cl += 1
        out += "%sreturn %s[s.upper()]\n" % (cl*indent*' ', self.get_class_name())
        cl -= 1

        # Error handling
        cl -= 1
        out += "%sexcept KeyError:\n" % (cl*indent*' ')
        cl += 1
        out += "%sraise argparse.ArgumentError()\n" % (cl*indent*' ')
        cl -= 1
        out += "%sexcept ValueError:\n" % (cl*indent*' ')
        cl += 1
        out += "%sraise argparse.ArgumentError()\n" % (cl*indent*' ')
        cl -= 1

        out += "\n"
        # indent to requested level
        out = shift_indent_level(out, indent, level)
        return out

    def get_enum_hash_py_def(self, indent=4, level=0):
        """Generate __hash__ function for enum to be able to use enum in dictionaries"""
        cl = 0
        out = "def __hash__(self):\n"
        cl += 1
        out += "%sreturn hash((self.name, self.value))\n\n" % (cl*indent*' ')
        # indent to requested level
        out = shift_indent_level(out, indent, level)
        return out

    def get_enum_default_py_def(self, indent=4, level=0):
        """Generate function which return default value for enum"""
        cl = 0
        out = "@staticmethod\n"
        out += "def default():\n"
        cl += 1
        out += "%sreturn %s.%s\n" % (cl*indent*' ', self.get_class_name(),
                                     self.get_lowest_enum().name.upper())
        out += "\n"
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

    def get_lowest_enum(self):
        """Get lowest enum"""
        # Work on copy of entry because sort() works in place
        entries = list(self.entries)
        entries.sort()
        return entries[0]



class DefsGen(object):
    instance = None
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
        self.bitfields = list()
        DefsGen.instance = self

        self.process_enums_defs()
        self.process_types_defs()
        self.process_bitfields_defs()
        self.process_messages_defs()

    def get_enum(self, name):
        """Return Enum from its name

        return None when there is no match
        """
        for e in self.enums:
            if e.name == name:
                return e
        return None

    def get_bitfield(self, name):
        """Return Bitfield from its name

        return None when there is no match
        """
        for bf in self.bitfields:
            if bf.name == name:
                return bf
        return None

    def process_messages_defs(self):
        """Read message definitions and build objects accordingly"""
        if "messages" not in self.defs.keys():
            return
        for m in self.defs["messages"]:
            msg_elt = MessageElt(m)
            self.messages.append(msg_elt)
        # Check unicity of messages names
        msg_names = [m.name for m in self.messages]
        dups = set([n for n in msg_names if msg_names.count(n) > 1])
        assert len(msg_names) == len(set(msg_names)), "found %s message(s) duplicated" % (', '.join(dups))

        # Check unicity of messages names
        msg_ids = [m.id for m in self.messages]
        dups = set([n for n in msg_ids if msg_ids.count(n) > 1])
        assert len(msg_ids) == len(set(msg_ids)), "found message id %r duplicated" % (dups)

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

    def process_bitfields_defs(self):
        """Read bitfields definitions"""
        if "bitfields" not in self.defs.keys():
            return
        for bf in self.defs["bitfields"]:
            bf = BitField(bf)
            self.bitfields.append(bf)

    def get_h_header(self):
        define = "__" + self.filename_prefix.upper() + "_H__"
        s = "#ifndef %s\n" % define
        s += "#define %s\n\n" % define
        s += "#include <stdint.h>\n\n"
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
        s += "import argparse\n"
        s += "import struct\n\n\n"
        return s

    def get_update_subparsers_py_def(self, indent=4, level=0):
        """Return function which update parser with subparsers for each message"""
        out = "def update_subparsers(subparsers):\n"
        if len(self.messages) == 0:
            out += "%sreturn\n" % (indent*' ')
        for m in self.messages:
            if m.id is None:
                continue
            out += "%smsg_map['%s'].get_argparse_group(subparsers)\n" % (indent*' ',
                                                                         m.get_class_name())
        out += "\n\n"
        # indent to requested level
        out = shift_indent_level(out, indent, level)
        return out

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
        out += "%sreturn data\n\n\n" % (indent_prefix)

        # indent to requested level
        out = shift_indent_level(out, indent, level)
        return out

    def get_autotest_py_def(self, indent=4, level=0):
        out = "def autotest():\n"
        if len(self.messages) == 0:
            out += "%sreturn\n" % (indent*' ')
        for m in self.messages:
            out += "%s%s.autotest()\n" % (indent*' ', snake_to_camel(m.name))
        out += "\n\n"

        # indent to requested level
        out = shift_indent_level(out, indent, level)
        return out

    def process_defs(self):
        if self.h_gen:
            h_file = self.h_dest + "/" + self.filename_prefix + ".h"
            with open(h_file, 'w') as h_fd:
                h_fd.write(self.get_h_header())

                # Write Enums C definitions
                for e in self.enums:
                    h_fd.write(e.get_enum_c_def())

                # Write Bitfield C definitions
                for bf in self.bitfields:
                    h_fd.write(bf.get_bitfield_c_defines())

                # Write Messages C definitions
                for m in self.messages:
                    h_fd.write(m.get_define_msg_id_def())
                    h_fd.write(m.get_struct_c_def())

                # Finish file with footer
                h_fd.write(self.get_h_footer())

        if self.py_gen:
            py_file = self.py_dest + "/" + self.filename_prefix + ".py"
            with open(py_file, 'w') as py_fd:
                py_fd.write(self.get_py_header())

                # Write Enums python definitions
                for e in self.enums:
                    py_fd.write(e.get_enum_py_def())

                for bf in self.bitfields:
                    py_fd.write(bf.get_class_py_def())

                # Write Messages python definitions
                for m in self.messages:
                    py_fd.write(m.get_class_py_def())

                py_fd.write(self.get_msg_creator_py_def())
                py_fd.write(self.get_update_subparsers_py_def())
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
