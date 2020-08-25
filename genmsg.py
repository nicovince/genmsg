#!/usr/bin/env python3
import re
from ruamel import yaml
import os
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


def count_last_empty_lines(s):
    """Count Empty lines at end of s"""
    cnt = 0
    lines = s.splitlines()
    lines.reverse()
    for l in lines:
        if re.match("^\s*$", l):
            cnt += 1
        else:
            return cnt
    return cnt

def bitwidth_to_ctype(bitwidth):
    if bitwidth <= 8:
        return "uint8_t"
    elif bitwidth <= 16:
        return "uint16_t"
    elif bitwidth <= 32:
        return "uint32_t"
    else:
        return None


def codegen(n=1):
    """decorator for methods which generates code

    n : number of empty line at the end of the generated code
    Decorated method MUST have indent and level as last args
    Decorated method MUST inherits of class CodeGen
    """
    def wrap(func):
        def wrap_func(*args):
            """Decorated function"""
            self = args[0]
            level = args[-1]
            indent = args[-2]
            # Save buffer and level of indentation
            save_code = self.current_code
            save_lvl = self.current_level
            self.flush_code()
            self.indent_size = indent
            out = func(*args)
            out = self.finish_statement(out, n)
            out = shift_indent_level(out, indent, level)
            # Restore buffer and level of indentation
            self.current_code = save_code
            self.current_level = save_lvl
            return out
        return wrap_func
    return wrap


class CodeGen(object):
    def __init__(self):
        # current level of indentation
        self.current_level = 0
        # Number of space per indentation
        self.indent_size = 4
        # buffer of code
        self.current_code = ""

    def indent(self, lvl=1):
        """Indent by specified number of level

        lvl can be positive or negative as long as current_level does not become negative
        """
        self.current_level += lvl
        assert self.current_level >= 0, "Level of indentation cannot become negative"""

    def deindent(self, lvl=1):
        """Deindent by specified number of level

        lvl can be positive or negative as long as current_lvel does not become negative
        """
        self.indent(-lvl)

    def blankline(self, n=1):
        """Insert specified number of blank lines"""
        for i in range(n):
            self.current_code += "\n"

    def code(self, s, newline=True):
        """Adds a line of code to current buffer of code

        The indentation is automatically added at the beginning of the line when required
        newline: when true a carriage return is added"
        """
        # indentation required if current buffer is empty or if last char of
        # buffer is a carriage return
        if len(self.current_code) == 0 or self.current_code[-1] == "\n":
            self.current_code += self.current_level * self.indent_size * ' '
        # Add requested line
        self.current_code += s
        # Add newline if requested
        if newline:
            self.current_code += "\n"

    def codeblock(self, blk):
        """Adds a block of code to current buffer of code

        Indentation is added for each lines of blk
        """
        lines = blk.splitlines()
        for l in lines:
            # Adds indentation on non empty lines
            if re.match("^\s*$", l) is None:
                self.current_code += self.current_level * self.indent_size * ' '
                self.current_code += l
            self.current_code += "\n"

    @classmethod
    def finish_statement(cls, statement, n):
        """Make sure statement ends with requested number of line

        statement: string to finish with selected number of lines
        n: number of lines that must finish the statement
        """
        empty_lines = count_last_empty_lines(statement)
        out = statement
        if empty_lines < n:
            for i in range(n-empty_lines):
                out += "\n"
        elif empty_lines > n:
            out = statement[:n - empty_lines]
        return out

    def shift(self, level):
        """Shift code by level of indentation"""
        self.current_code = shift_indent_level(self.current_code,
                                               self.indent_size, level)

    def flush_code(self):
        """Flush current buffer of code"""
        self.current_code = ""
        self.current_level = 0


class Bits(CodeGen):
    """Bits description within a bitfield

    Describe one or more bit in a bitfield with a name, position, width, description.
    An enumeration can be attached to a bits description
    """
    def __init__(self, name, position, desc, prefix, width=1):
        """Bits initializer

        name: string describing the bit(s)
        position: index within the bitfield of the LSB of the bit(s),
        desc: string giving a description of what the bit(s) do
        prefix: prefix for bitname
        width: size of the bits
        """
        CodeGen.__init__(self)
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
        return (1 << self.width) - 1

    @codegen(1)
    def get_bits_c_def(self, indent=4, level=0):
        """Return string with C define for bits description"""
        self.code("/* %s */" % (self.desc))
        # Bits position and mask if width > 1
        if self.width == 1:
            self.code("#define %s (1 << %d)" % (self.get_bits_name(), self.position))
        else:
            self.code("#define %s_MASK (0x%x << %d)" % (self.get_bits_name(),
                                                        self.get_bits_mask(),
                                                        self.position))
            self.code("#define %s_POS %d" % (self.get_bits_name(), self.position))

        # Enums shifted to bits position
        if self.enum is not None:
            enum_def = DefsGen.instance.get_enum(self.enum)
            for e in enum_def.entries:
                enum_prefix = self.get_bits_name()
                self.code("#define %s_%s (%s << %s_POS)" % (enum_prefix,
                                                            e.get_enum_name(),
                                                            e.get_enum_name(),
                                                            self.get_bits_name()))

        return self.current_code

    @codegen(0)
    def get_bits_c_struct_field(self, indent=4, level=0):
        """Return string with definition of a field in a bitfield"""
        self.code("%s %s : %d; /* %s */" % (bitwidth_to_ctype(self.width),
                                            self.name, self.width, self.desc),
                  False)
        return self.current_code

    def get_class_name(self):
        suffix = "_bit"
        if self.width > 1:
            suffix += "s"
        return snake_to_camel(self.name + suffix)

    @codegen()
    def get_init_py_def(self, indent=4, level=0):
        """Return class initializer"""
        self.code("def __init__(self, value):")
        self.indent()
        self.code("self.value = value")
        return self.current_code

    @codegen()
    def get_str_py_def(self, indent=4, level=0):
        """Return __str__ method for Bit"""
        self.code("def __str__(self):")
        self.indent()
        self.code("return \"%s: %%s\" %% (self._value)" % (self.name))
        return self.current_code

    @codegen()
    def get_eq_py_def(self, indent=4, level=0):
        """Return __eq__ method for Bit"""
        self.code("def __eq__(self, other):")
        self.indent()
        self.code("return self.value == other.value")
        return self.current_code

    @codegen()
    def get_repr_py_def(self, indent=4, level=0):
        """Return __repr__ method for Bit"""
        self.code("def __repr__(self):")
        self.indent()
        self.code("return \"%s(" % (self.get_class_name()), False)
        self.code("value=%s)\" % (str(self.value))")
        return self.current_code

    @codegen()
    def get_getter_py_def(self, indent=4, level=0):
        """Return getter definition"""
        self.code("@property")
        self.code("def value(self):")
        self.indent()
        self.code("return self._value")
        return self.current_code

    @codegen()
    def get_setter_py_def(self, indent=4, level=0):
        """Return setter definition"""
        self.code("@value.setter")
        self.code("def value(self, value):")
        self.indent()
        # verify value is within range
        if self.enum is None:
            # Check value passed to setter is in valid range or is of the current class
            if self.width == 1:
                self.code("assert isinstance(value, self.__class__) or ", False)
                self.code("(value == 0) or (value == 1), ", False)
                self.code("\"Invalid value %%d for bit %s\" %% (value)" % (self.name))
            else:
                self.code("assert isinstance(value, self.__class__) or ", False)
                self.code("((value | 0x%x) >> %d) == 0, " % (self.get_bits_mask(),
                                                             self.width),
                          False)
                self.code("\"Invalid value %%d for bit %s\" %% (value)\n" % (self.name))
        else:
            # Check value passed to setter is of the current class, the
            # appropriate enum or enum value
            enum_def = DefsGen.instance.get_enum(self.enum)
            self.code("assert isinstance(value, self.__class__) or ", False)
            self.code("value.__class__.__name__ == \"%s\" or " % (enum_def.get_class_name()),
                      False)
            self.code("value in [e.value for e in list(%s)], " % (enum_def.get_class_name()),
                      False)
            self.code("\"Invalid value %%r for bit %s, must be of kind %s\" %% (value)" % (self.name,
                                                                                           enum_def.get_class_name()))

        self.code("if isinstance(value, self.__class__):")
        self.indent()
        self.code("self._value = value.value")
        self.deindent()
        if self.enum is not None:
            self.code("elif isinstance(value, int):")
            self.indent()
            self.code("self._value = %s(value)" % (enum_def.get_class_name()))
            self.deindent()
        self.code("else:")
        self.indent()
        self.code("self._value = value")
        return self.current_code

    @codegen()
    def get_pack_py_def(self, indent=4, level=0):
        """Return bit packing function"""
        cl = 0
        self.code("def pack(self):")
        self.indent()
        if self.enum is None:
            self.code("return self._value << %d" % (self.position))
        else:
            self.code("return self._value.value << %d" % (self.position))
        return self.current_code

    @codegen()
    def get_unpack_py_def(self, indent=4, level=0):
        """Return Bit unpacking function"""
        cl = 0
        self.code("@classmethod")
        self.code("def unpack(cls, data):")
        self.indent()
        self.code("value = (data >> cls.position) & ((1 << cls.width) - 1)")
        self.code("return cls(value)")
        return self.current_code

    @codegen()
    def get_rand_py_def(self, indent=4, level=0):
        """Return rand function"""
        cl = 0
        self.code("@classmethod")
        self.code("def rand(cls):")
        self.indent()
        if self.enum is None:
            self.code("min_val = 0")
            self.code("max_val = 0x%x" % (self.get_bits_mask()))
            self.code("value = random.randint(min_val, max_val)")
        else:
            enum_def = DefsGen.instance.get_enum(self.enum)
            self.code("value = random.choice(list(%s))" % (enum_def.get_class_name()))

        self.code("return cls(value)")
        return self.current_code

    @codegen(1)
    def get_class_py_def(self, indent, level):
        """Return Bit Class Definition"""
        self.code("class %s(object):" % (self.get_class_name()))
        self.indent()
        self.code("\"\"\"%s\"\"\"" % (self.desc))
        self.code("position = %d" % (self.position))
        self.code("width = %d" % (self.width))
        self.code("name = \"%s\"" % (self.name))
        self.blankline()
        self.codeblock(self.get_init_py_def(indent, 0))
        self.codeblock(self.get_str_py_def(indent, 0))
        self.codeblock(self.get_eq_py_def(indent, 0))
        self.codeblock(self.get_repr_py_def(indent, 0))
        self.codeblock(self.get_pack_py_def(indent, 0))
        self.codeblock(self.get_unpack_py_def(indent, 0))
        self.codeblock(self.get_rand_py_def(indent, 0))
        self.codeblock(self.get_getter_py_def(indent, 0))
        self.codeblock(self.get_setter_py_def(indent, 0))

        return self.current_code


class BitField(CodeGen):
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
        CodeGen.__init__(self)
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
                enum_width = enum_def.get_enum_bit_width()
                if enum_width != bit.width:
                    print("Warning: width of field %s is %d, attached enum %s width is %d. Override field width." % (bit.name, bit.width, enum_name, enum_width))
                bit.width = enum_width

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
        return bitwidth_to_ctype(bitwidth)

    @codegen()
    def get_bitfield_c_defines(self, indent, level):
        """Return string containing defines for bitfield"""
        if self.name is not None:
            self.code("/* %s bitfield */" % (self.name))

        for bit in self.bits:
            self.code(bit.get_bits_c_def(indent, level))
        return self.current_code

    @codegen()
    def get_bitfield_c_struct(self, indent, level):
        self.code("/* %s bitfield structure */" % (self.name))
        self.code("typedef struct {")
        for bit in self.bits:
            self.code(bit.get_bits_c_struct_field(indent, level + 1))
        self.code("} %s_t;" % self.name)

        return self.current_code

    def get_class_name(self):
        return snake_to_camel(self.name + "_bit_field")

    @codegen()
    def get_init_py_def(self, indent=4, level=0):
        """Return BitField Initializer"""
        bits = list(self.bits)
        bits.sort()
        bits_names = [b.name for b in bits]
        self.code("def __init__(self, %s):" % (', '.join(bits_names)))
        self.indent()
        for b in bits:
            self.code("self._%s = self.%s(%s)" % (b.name, b.get_class_name(),
                                                  b.name))
        return self.current_code

    @codegen()
    def get_str_py_def(self, indent=4, level=0):
        """Return __str__ method for BitField"""
        self.code("def __str__(self):")
        self.indent()
        self.code("out = \"\"")
        bits = list(self.bits)
        bits.sort()
        bits.reverse()
        for b in bits:
            self.code("out += \"%%s\\n\" %% (self._%s)" % (b.name))
        self.code("return out")
        return self.current_code

    @codegen()
    def get_eq_py_def(self, indent=4, level=0):
        """Return __eq__ method for BitField"""
        self.code("def __eq__(self, other):")
        self.indent()
        self.code("res = True")
        for b in self.bits:
            self.code("res = res and (self.%s == other.%s)" % (b.name, b.name))
        self.code("return res")
        return self.current_code

    @codegen()
    def get_pack_py_def(self, indent=4, level=0):
        """Return function which packs all bitfields"""
        self.code("def pack(self):")
        self.indent()
        self.code("\"\"\"Pack each bit of bitfield and return packed integer.\"\"\"")
        self.code("ret = 0")
        bits = list(self.bits)
        bits.sort()
        bits.reverse()
        for b in bits:
            self.code("ret |= self.%s.pack()" % (b.name))
        self.code("return ret")
        return self.current_code

    @codegen()
    def get_unpack_py_def(self, indent=4, level=0):
        """Return BitField Unpacking function"""
        self.code("@classmethod")
        self.code("def unpack(cls, data):")
        self.indent()
        for b in self.bits:
            self.code("%s = cls.%s.unpack(data)" % (b.name, b.get_class_name()))
        self.code("return cls(", False)
        for b in self.bits:
            self.code("%s=%s, " % (b.name, b.name), False)
        self.code(")")
        return self.current_code

    @codegen()
    def get_rand_py_def(self, indent=4, level=0):
        """Return rand function"""
        self.code("@classmethod")
        self.code("def rand(cls):")
        self.indent()
        for b in self.bits:
            self.code("%s = cls.%s.rand()" % (b.name, b.get_class_name()))

        self.code("return %s(" % (self.get_class_name()), False)
        for b in self.bits:
            self.code("%s=%s, " % (b.name, b.name), False)
        self.code(")")
        return self.current_code

    @codegen()
    def get_getters_py_def(self, indent=4, level=0):
        """Return getters for each bit of the bitfield"""
        for b in self.bits:
            self.code("@property")
            self.code("def %s(self):" % (b.name))
            self.indent()
            self.code("return self._%s\n" % (b.name))
            self.deindent()
        return self.current_code

    @codegen()
    def get_setters_py_def(self, indent=4, level=0):
        """Return setters for each bit of the bitfield"""
        for b in self.bits:
            self.code("@%s.setter" % (b.name))
            self.code("def %s(self, value):" % (b.name))
            self.indent()
            self.code("self._%s.value = value\n" % (b.name))
            self.deindent()
        return self.current_code

    @codegen(2)
    def get_class_py_def(self, indent, level):
        """Return string with python class declaration for BitField"""
        self.code("class %s(object):" % (self.get_class_name()))
        self.indent()
        self.code("\"\"\"%s\"\"\"" % (self.desc))
        # define class for each bit(s) definition
        for b in self.bits:
            self.codeblock(b.get_class_py_def(indent, 0))

        self.codeblock(self.get_init_py_def(indent, 0))
        self.codeblock(self.get_getters_py_def(indent, 0))
        self.codeblock(self.get_setters_py_def(indent, 0))
        self.codeblock(self.get_str_py_def(indent, 0))
        self.codeblock(self.get_eq_py_def(indent, 0))
        self.codeblock(self.get_pack_py_def(indent, 0))
        self.codeblock(self.get_unpack_py_def(indent, 0))
        self.codeblock(self.get_rand_py_def(indent, 0))
        return self.current_code


class StructField(CodeGen):
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
        CodeGen.__init__(self)
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

        Either a struct or ctype.
        """
        return re.sub("\[\d*\]", "", self.field_type)

    def is_bitfield(self):
        bf = DefsGen.instance.get_bitfield(self.field_type)
        return bf is not None

    def is_ctype(self):
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
        if not(self.is_ctype()) and not self.is_bitfield():
            return snake_to_camel(self.get_base_type())
        elif self.is_bitfield():
            bf = DefsGen.instance.get_bitfield(self.field_type)
            return bf.get_class_name()

    def get_field_fmt(self):
        """Return format used by struct for the whole field
        This includes leading %d if the field is an array or complex type
        """
        if self.is_ctype() or self.is_bitfield():
            if self.is_ctype():
                fmt = self.ctype_to_struct_fmt[self.get_base_type()]
            else:
                bf = DefsGen.instance.get_bitfield(self.field_type)
                fmt = self.ctype_to_struct_fmt[bf.get_base_type()]
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

    @codegen(0)
    def get_argparse_decl(self, parser_name, indent=4, level=0):
        """Return instruction to register option to parser"""
        help_str = "help='%s'" % self.desc
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
                self.code("enum_help = list()")
                self.code("for e in [e.value for e in %s]:" % (snake_to_camel(self.enum)))
                self.indent()
                self.code("enum_help.append(\"%%d: %%s\" %% (e, %s(e).name.lower()))" % (snake_to_camel(self.enum)))

                self.deindent()
                help_str = "help='%s (%%s)' %% (' - '.join(enum_help))" % (self.desc)
            # nargs
            if self.is_array():
                if self.array_len > 0:
                    nargs = "nargs=%d, " % self.array_len
                else:
                    nargs = "nargs='+', "
            else:
                nargs = ""
            self.code("%s.add_argument('--%s', %s%s%s%s%s%s)" % (parser_name,
                                                                 self.name,
                                                                 argtype,
                                                                 nargs,
                                                                 choices,
                                                                 metavar,
                                                                 default,
                                                                 help_str))
        else:
            # TODO Fix default
            default = [0xA, 0xB]
            self.code("%s.add_argument('--%s', nargs='*', default=%s, %s)" % (parser_name,
                                                                              self.name,
                                                                              default,
                                                                              help_str))
        return self.current_code


class MessageElt(CodeGen):
    """Message object created from dictionary definition"""
    def __init__(self, message):
        CodeGen.__init__(self)
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

    @codegen()
    def get_struct_c_def(self, indent, level):
        """Return string with C struct declaration of messages"""
        self.code("/* %s */" % (self.desc))
        if len(self.fields) > 0:
            self.code("#pragma pack(push, 1)")
            self.code("typedef struct {")
            self.indent();

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

                self.code("%s %s%s; /* %s */" % (type_str, f.name,
                                                 array_suffix, f.desc))

            self.deindent()
            self.code("} %s_t;" % (self.name))
            self.code("#pragma pack(pop)")
        else:
            self.code("/* No Fields for this message */")

        return self.current_code

    def get_define_msg_name(self):
        return self.name.upper() + "_ID"

    @codegen(0)
    def get_define_msg_id_def(self, indent, level):
        if self.id is not None:
            self.code("#define %s %d" % (self.get_define_msg_name(), self.id))
        return self.current_code

    @codegen(2)
    def get_class_py_def(self, indent, level):
        """Return string with python class declaration"""
        current_level = 0

        # Class definition
        self.code("class %s(object):" % snake_to_camel(self.name))
        self.indent()
        self.code("\"\"\"%s\"\"\"" % (self.desc))
        self.code("n_fields = %d" % (len(self.fields)))
        if self.id is not None:
            self.code("msg_id = %d" % (self.id))
        self.blankline()

        # methods
        self.codeblock(self.get_init_py_def(indent, 0))
        self.codeblock(self.get_repr_py_def(indent, 0))
        self.codeblock(self.get_str_py_def(indent, 0))
        self.codeblock(self.get_eq_py_def(indent, 0))
        self.codeblock(self.get_len_py_def(indent, 0))
        self.codeblock(self.get_n_fields_py_def(indent, 0))
        self.codeblock(self.get_fields_py_def(indent, 0))
        self.codeblock(self.get_struct_fmt_py_def(indent, 0))
        self.codeblock(self.get_unpack_struct_fmt_py_def(indent, 0))
        self.codeblock(self.get_pack_py_def(indent, 0))
        self.codeblock(self.get_unpack_py_def(indent, 0))
        self.codeblock(self.get_helper_def(indent, 0))
        self.codeblock(self.get_rand_py_def(indent, 0))
        self.codeblock(self.get_autotest_py_def(indent, 0))
        self.codeblock(self.get_argparse_group_py_def(indent, 0))
        self.codeblock(self.get_args_handler(indent, 0))
        return self.current_code

    @codegen()
    def get_init_py_def(self, indent, level):
        """Return initializer method"""
        # Field names of Message
        field_names = [f.name for f in self.fields]

        self.code("def __init__(self, %s):" % (', '.join(field_names)))
        self.indent()
        # assign fields
        for f in self.fields:
            if f.enum is not None and not(f.is_array()):
                self.code("assert %s in %s, \"Invalid value for %s (%%s)\" %% (%s)" % (f.name,
                                                                                       snake_to_camel(f.enum),
                                                                                       f.name,
                                                                                       f.name))
            elif f.enum is not None and f.is_array():
                self.code("for v in %s:" % (f.name))
                self.indent()
                self.code("assert v in %s, \"Invalid value for %s (%%s)\" %% (%s)" % (snake_to_camel(f.enum),
                                                                                      f.name, f.name))
                self.deindent()
            self.code("self.%s = %s" % (f.name, f.name))
        self.code("return\n")
        return self.current_code

    @codegen()
    def get_n_fields_py_def(self, indent, level):
        """Return method that compute number of fields in message
        This includes number of fields in complex type fields
        """
        self.code("@classmethod")
        self.code("def get_n_fields(cls):")
        self.indent()
        self.code("n = 0")
        self.code("suffix = ''")
        for f in self.fields:
            if f.is_ctype() or f.is_bitfield():
                if not(f.is_array()):
                    self.code("n += 1  # %s" % (f.name))
                else:
                    if f.array_len > 0:
                        self.code("n += %d  # %s" % (f.array_len, f.name))
                    else:
                        self.code("suffix = '+'  # %s" % (f.name))
                        self.code("n += 1  # %s" % (f.name))
            else:
                self.code("(%s_n, %s_suffix) = %s.get_n_fields()" % (f.name, f.name,
                                                                     f.get_class_name()))
                self.code("n += %s_n" % (f.name))
                self.code("suffix = %s_suffix" % (f.name))
        self.code("return (n, suffix)")
        return self.current_code

    @codegen()
    def get_struct_fmt_py_def(self, indent=4, level=0):
        """Return method that dynamically compute struct format"""
        # Current level of indentation
        self.code("@staticmethod")
        self.code("def struct_fmt(data):")
        self.indent()
        self.code("fmt = \"\"")
        for f in self.fields:
            if f.is_ctype() or f.is_bitfield():
                if not(f.is_array()) or (f.array_len > 0):
                    self.code("fmt += \"%s\"" % (f.get_field_fmt()))
                else:
                    self.code("fmt += \"%s\" %% (len(data))" % (f.get_field_fmt()))
            else:
                # Complex type
                if not(f.is_array()):
                    self.code("fmt += %s.struct_fmt(data)" % (f.get_class_name()))
                elif f.is_array() and f.array_len > 0:
                    self.code("for e in range(%d):" % (f.array_len))
                    self.indent()
                    self.code("fmt += %s.struct_fmt(data)" % (f.get_class_name()))
                    self.deindent()
                else:
                    self.code("for e in range(len(data)):")
                    self.indent()

                    self.code("fmt += %s.struct_fmt(data)" % (f.get_class_name()))
                    self.deindent()

        self.code("return fmt")
        return self.current_code

    @codegen()
    def get_pack_py_def(self, indent=4, level=0):
        """Return packing function"""
        # Field names of message
        field_names = [f.name for f in self.fields]
        array_name = "None"
        for f in self.fields:
            if f.is_array():
                array_name = "self.%s" % (f.name)

        # pack method definition
        self.code("def pack(self):")
        self.indent()
        pack_va = ", ".join([f.get_pack_va() for f in self.fields])
        self.code("va_args = list()")
        for f in self.fields:
            if f.is_ctype() or f.is_bitfield():
                suffix = ""
                if f.enum is not None:
                    suffix = ".value"
                elif f.is_bitfield():
                    suffix = ".pack()"

                if not(f.is_array()):
                    self.code("va_args.append(self.%s%s)" % (f.name, suffix))
                else:
                    self.code("va_args.extend([e%s for e in self.%s])" % (suffix,
                                                                          f.name))
            else:
                if not(f.is_array()):
                    self.code("va_args.extend(self.%s.get_fields())" % (f.name))
                else:
                    self.code("for e in self.%s:" % (f.name))
                    self.indent()
                    self.code("va_args.extend(e.get_fields())")
                    self.deindent()

        self.code("fmt = \"<%%s\" %% (self.struct_fmt(%s))" % (array_name))
        self.code("return struct.pack(fmt, *va_args)")
        return self.current_code

    @codegen()
    def get_fields_py_def(self, indent=4, level=0):
        """Return method definition that return tuple of fields"""
        self.code("def get_fields(self):")
        self.indent()
        field_names = [f.name for f in self.fields]
        self.code("ret = list()")
        for f in self.fields:
            suffix = ""
            if f.enum is not None:
                suffix = ".value"
            self.code("ret.append(self.%s%s)" % (f.name, suffix))
        self.code("return ret")
        return self.current_code

    @codegen()
    def get_repr_py_def(self, indent=4, level=0):
        """return __repr__ method for message"""
        # Field names of message
        field_names = [f.name for f in self.fields]
        self.code("def __repr__(self):")
        self.indent()
        self.code("return \"%s(" % (snake_to_camel(self.name)), False)
        if len(field_names) > 0:
            self.code("%s=%%r" % ('=%r, '.join(field_names)), False)
            self.code(")\" %% (self.%s)" % (', self.'.join(field_names)))
        else:
            self.code(")\"")
        return self.current_code

    @codegen()
    def get_str_py_def(self, indent=4, level=0):
        """return __str__ method for message"""
        # Field names of message
        self.code("def __str__(self):")
        self.indent()
        self.code("out = \"%s:\\n\"" % (self.name))
        for f in self.fields:
            if f.enum is None:
                self.code("out += \"  %s: %%s\\n\" %% (str(self.%s))" % (f.name, f.name))
            else:
                if not(f.is_array()):
                    self.code("out += \"  %s: %%s\\n\" %% (%s(self.%s).name)" % (f.name,
                                                                                 snake_to_camel(f.enum),
                                                                                 f.name))
                else:
                    self.code("l = [%s(v).name for v in self.%s]" % (snake_to_camel(f.enum),
                                                                     f.name))
                    self.code("out += \"  %s: %%s\\n\" %% (l)" % (f.name))
        self.code("return out")
        return self.current_code

    @codegen()
    def get_len_py_def(self, indent=4, level=0):
        """Return method capable of counting message object length"""
        self.code("def __len__(self):")
        self.indent()
        array_name = "None"
        for f in self.fields:
            if f.is_array():
                array_name = "self.%s" % f.name
                break

        self.code("return struct.calcsize('<%%s' %% self.struct_fmt(%s))" % (array_name))
        return self.current_code

    @codegen()
    def get_eq_py_def(self, indent=4, level=0):
        """Return __eq__ method"""
        self.code("def __eq__(self, other):")
        self.indent()
        self.code("res = True")
        for f in self.fields:
            self.code("res = res and (self.%s == other.%s)" % (f.name, f.name))
        self.code("return res")
        return self.current_code

    @codegen()
    def get_rand_py_def(self, indent=4, level=0):
        """Return method which create a random message"""
        self.code("@classmethod")
        self.code("def rand(cls):")
        self.indent()
        byte_offset = 0
        for f in self.fields:
            if f.is_ctype() or f.is_bitfield():
                if f.is_bitfield():
                    rand_func = "%s.rand" % (f.get_class_name())
                    population_str = ""
                elif f.enum is None:
                    population_str = "range(%d, %d)" % (f.get_range()[0], f.get_range()[1])
                    rand_func = "random.choice"
                else:
                    rand_func = "random.choice"
                    population_str = "list(%s)" % (snake_to_camel(f.enum))

                if f.is_array() and not(f.array_len > 0):
                    self.code("%s = [%s(%s) for e in range(random.randint(0, %d))]" % (f.name,
                                                                                       rand_func,
                                                                                       population_str,
                                                                                       256-byte_offset))
                elif f.is_array() and (f.array_len > 0):
                    self.code("%s = [%s(%s) for e in range(%d)]" % (f.name,
                                                                    rand_func,
                                                                    population_str,
                                                                    f.array_len))
                elif f.is_bitfield():
                    print(f.get_class_name())
                    self.code("%s = %s.rand()" % (f.name,
                                                  f.get_class_name()))
                else:
                    if f.enum is None:
                        self.code("%s = random.randint(*%s)" % (f.name,
                                                                f.get_range()))
                    else:
                        self.code("%s = random.choice(%s)" % (f.name,
                                                              population_str))

            else:
                if f.is_array():
                    if f.array_len > 0:
                        n = f.array_len
                        self.code("%s = [%s.rand() for e in range(%d)]" % (f.name,
                                                                           snake_to_camel(f.get_base_type()),
                                                                           n))
                    else:
                        # TODO: use space left instead of 255
                        self.code("n = random.randint(1, int(255/struct.calcsize(%s.struct_fmt(None))))" % (f.get_class_name()))
                        self.code("%s = [%s.rand() for e in range(int(n))]" % (f.name,
                                                                               f.get_class_name()))
                else:
                    self.code("%s = %s.rand()" % (f.name,
                                                  snake_to_camel(f.field_type)))

        self.code("return %s(" % (snake_to_camel(self.name)), False)
        for f in self.fields:
            self.code("%s=%s, " % (f.name, f.name), False)

        self.code(")")
        return self.current_code

    @codegen()
    def get_args_handler(self, indent=4, level=0):
        """Return method which process args and return object"""
        self.code("@classmethod")
        self.code("def args_handler(cls, args):")
        self.indent()
        args = ""
        for f in self.fields:
            if len(args) > 0:
                args += ", "
            args += "%s=args.%s" % (f.name, f.name)

        self.code("return %s(%s)" % (self.get_class_name(), args))
        return self.current_code

    @codegen()
    def get_argparse_group_py_def(self, indent=4, level=0):
        """Return method adding option group to subparser for current message"""
        self.code("@classmethod")
        self.code("def get_argparse_group(cls, subparser):")
        self.indent()
        parser_name = "parser_%s" % (self.name)
        formatter_class_str = "formatter_class=argparse.ArgumentDefaultsHelpFormatter"
        self.code("%s = subparser.add_parser('%s', %s, help='%s')" % (parser_name,
                                                                      self.name,
                                                                      formatter_class_str,
                                                                      self.desc))
        for f in self.fields:
            if f.is_ctype() or f.is_bitfield():
                self.codeblock("%s" % (f.get_argparse_decl(parser_name, indent, 0)))
            else:
                self.codeblock(self.get_argparse_decl(parser_name, f, indent, 0))
        self.code("%s.set_defaults(func=%s.args_handler)" % (parser_name,
                                                             self.get_class_name()))
        return self.current_code

    @codegen(0)
    def get_argparse_decl(self, parser_name, field, indent=4, level=0):
        """Return instruction to register option to parser
        The fields are given as raw data"""
        self.code("(nargs, suffix) = %s.get_n_fields()" % (field.get_class_name()))
        self.code("%s.add_argument('--%s', type=int, nargs=nargs)" % (parser_name, field.name,))
        return self.current_code

    @codegen()
    def get_autotest_py_def(self, indent=4, level=0):
        """Return method testing the class"""
        self.code("@classmethod")
        self.code("def autotest(cls):")
        self.indent()
        self.code("inst1 = cls.rand()")
        self.code("print(inst1.pack())")
        self.code("print(str(inst1))")
        self.code("assert(inst1 == inst1.unpack(inst1.pack()))")
        return self.current_code

    @codegen()
    def get_unpack_struct_fmt_py_def(self, indent=4, level=0):
        self.code("@staticmethod")
        self.code("def get_unpack_struct_fmt(data):")
        self.indent()
        # Initialize empty format
        self.code("fmt = \"\"" % ())
        for f in self.fields:
            if f.is_ctype() or f.is_bitfield():
                if not(f.is_array()) or f.array_len > 0:
                    self.code("fmt += \"%s\"" % (f.get_field_fmt()))
                else:
                    # Unknown array size
                    # field format contains %d which needs to be computed at
                    # runtime
                    self.code("if type(data) == bytes:")
                    self.indent()
                    self.code("fmt += \"%s\" %% ((len(data) - struct.calcsize(fmt))/%s)" % (f.get_field_fmt(),
                                                                                            struct.calcsize(f.get_fmt())))
                    self.deindent()
                    self.code("else:")
                    self.indent()
                    self.code("fmt += \"%s\" %% (len(data))" % (f.get_field_fmt()))
                    self.deindent()
            else:
                # Complex type
                if not(f.is_array()):
                    self.code("offset = struct.calcsize(fmt)")
                    arg = "struct.calcsize(%s.get_unpack_struct_fmt(data[offset:]))" % (f.get_class_name())
                    self.code("fmt += \"%s\" %% (%s)" % (f.get_field_fmt(), arg))
                else:
                    # Array of complex type
                    if f.array_len > 0:
                        # Fixed size
                        self.code("for e in range(%d):" % (f.array_len))
                        self.indent()
                        arg = "struct.calcsize(%s.get_unpack_struct_fmt(None))" % (f.get_class_name())
                        self.code("fmt += \"%s\" %% (%s)" % (f.get_field_fmt(),
                                                             arg))
                        self.deindent()
                    else:
                        # variable size
                        self.code("header_sz = struct.calcsize('<%s' % (fmt))")
                        self.code("array_sz = len(data) - header_sz")
                        self.code("elt_sz = struct.calcsize(%s.struct_fmt(None))" % (f.get_class_name()))
                        self.code("for e in range(int(array_sz/elt_sz)):")
                        self.indent()
                        self.code("fmt += '%ds' % (elt_sz)")
                        self.deindent()
        self.code("return fmt\n")
        return self.current_code


    @codegen()
    def get_unpack_py_def(self, indent=4, level=0):
        """return unpack method which convert byte to message object"""
        # Field names of Message
        field_names = [f.name for f in self.fields]

        self.code("@classmethod")
        self.code("def unpack(cls, data):")
        self.indent()

        if len(self.fields) > 0:
            self.code("msg_fmt = \"<%s\" % (cls.get_unpack_struct_fmt(data))")
            self.code("unpacked = struct.unpack(msg_fmt, data)")

            # Assign each field from raw unpacked
            offset = 0
            for f in self.fields:
                if not(f.is_array()):
                    if f.is_bitfield():
                        bf = DefsGen.instance.get_bitfield(f.field_type)
                        self.code("%s = %s.unpack(unpacked[%d])" % (f.name,
                                                                    bf.get_class_name(),
                                                                    offset))
                        offset += 1
                    elif f.is_ctype():
                        if f.enum is None:
                            self.code("%s = unpacked[%d]" % (f.name, offset))
                        else:
                            self.code("%s = %s(unpacked[%d])" % (f.name,
                                                                 snake_to_camel(f.enum),
                                                                 offset))
                        offset += 1
                    else:
                        self.code("%s = unpacked[%d]" % (f.name, offset))
                        offset += 1
                else:
                    if f.is_ctype():
                        if (f.array_len > 0):
                            # Array size is known in advance,
                            # retrieve exact number of elements
                            self.code("%s = unpacked[%d:%d]" % (f.name,
                                                                offset,
                                                                offset + f.array_len))
                            offset += f.array_len
                        else:
                            # Array size is known at runtime only
                            # Such arrays *must* be at the end of the message definition,
                            # therefore we know there is nothing after.
                            self.code("%s = unpacked[%d:]" % (f.name, offset))
                        if f.enum is not None:
                            self.code("%s = [%s(e) for e in %s]" % (f.name,
                                                                    snake_to_camel(f.enum),
                                                                    f.name))
                    else:
                        # Complex type
                        if f.array_len > 0:
                            self.code("%s = unpacked[%d:%d]" % (f.name,
                                                                offset,
                                                                offset + f.array_len))
                            offset += f.array_len
                        else:
                            # Array size is known at runtime only
                            # Such arrays *must* be at the end of the message definition,
                            # therefore we know there is nothing after.
                            self.code("%s = unpacked[%d:]" % (f.name, offset))

            # Convert bytes of complex type to proper object
            for f in self.fields:
                if f.is_array():
                    self.code("%s = list(%s)" % (f.name, f.name))
                if not f.is_ctype() and not f.is_bitfield():
                    if not(f.is_array()):
                        self.code("%s = %s.unpack(%s)" % (f.name,
                                                          f.get_class_name(),
                                                          f.name))
                    else:
                        self.code("%s = [%s.unpack(e) for e in %s]" % (f.name,
                                                                       f.get_class_name(),
                                                                       f.name))

        self.code("return %s(" % (snake_to_camel(self.name)), False)
        for f in field_names:
            self.code("%s=%s, " % (f, f), False)
        self.code(")")
        return self.current_code

    @codegen()
    def get_helper_def(self, indent=4, level=0):
        """Return string which display message format to help out user"""
        self.code("@classmethod")
        self.code("def helper(cls):")
        self.indent()
        self.code("print(\"%s fields:\")" % (snake_to_camel(self.name)))
        for f in self.fields:
            self.code("print(\"  %s: %s\")" % (f.name, f.field_type))
        return self.current_code

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


class EnumElt(CodeGen):
    """Enumeration object created from dictionary definition"""
    def __init__(self, enum):
        CodeGen.__init__(self)
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

    @codegen()
    def get_enum_c_def(self, indent=4, level=0):
        """Return string with C enum declaration"""
        self.code("/* %s */" % (self.desc))
        self.code("typedef enum %s_e {" % (self.name))
        self.indent()
        max_enum_val = 0
        for e in self.entries:
            self.code("%s = %d, /* %s */" % (e.get_enum_name(), e.value, e.desc))
            max_enum_val = max(max_enum_val, e.value)
        self.code("%s_END = %d" % (self.name, max_enum_val+1))
        self.deindent()
        self.code("} %s_t;\n" % (self.name))
        return self.current_code

    @codegen(2)
    def get_enum_py_def(self, indent, level):
        """Return string with python enum declaration"""
        self.code("# %s" % (self.desc))
        self.code("class %s(Enum):" % (snake_to_camel(self.name)))
        self.indent()
        for e in self.entries:
            self.code("%s = %d  # %s" % (e.get_enum_name(), e.value, e.desc))

        self.blankline()
        self.deindent()

        self.codeblock(self.get_enum_eq_py_def(indent, level+1))
        self.codeblock(self.get_enum_type_py_def(indent, level+1))
        self.codeblock(self.get_enum_hash_py_def(indent, level+1))
        self.codeblock(self.get_enum_default_py_def(indent, level+1))

        return self.current_code

    def get_class_name(self):
        return snake_to_camel(self.name)

    @codegen()
    def get_enum_eq_py_def(self, indent=4, level=0):
        """Return function which compares enum"""
        self.code("def __eq__(self, other):")
        self.indent()
        self.code("# This is required because enum imported from different location fails equality tests")
        self.code("# First test the two object have the same class name")
        self.code("if other.__class__.__name__ == self.__class__.__name__:")
        self.indent()
        self.code("# Then check values")
        self.code("return self.value == other.value")
        self.deindent()
        self.code("else:")
        self.indent()
        self.code("return False")
        return self.current_code

    @codegen()
    def get_enum_type_py_def(self, indent=4, level=0):
        """Generate function used for 'type' parameter during argparse declaration"""
        self.code("def %s_type(s):" % (self.name))
        self.indent()
        self.code("\"\"\"Return Enum object from string representation\n")
        self.code("Used in type parameter of argparse declaration\"\"\"")
        self.code("try:")
        self.indent()
        self.code("if s.isdecimal():")
        # arg is decimal
        self.indent()
        self.code("return %s(int(s))" % (self.get_class_name()))
        self.deindent()
        self.code("else:")
        # Arg is enum string
        self.indent()
        self.code("return %s[s.upper()]" % (self.get_class_name()))
        self.deindent()

        # Error handling
        self.deindent()
        self.code("except KeyError:")
        self.indent()
        self.code("raise argparse.ArgumentError()")
        self.deindent()
        self.code("except ValueError:")
        self.indent()
        self.code("raise argparse.ArgumentError()")
        self.deindent()
        return self.current_code

    @codegen()
    def get_enum_hash_py_def(self, indent=4, level=0):
        """Generate __hash__ function for enum to be able to use enum in dictionaries"""
        self.code("def __hash__(self):")
        self.indent()
        self.code("return hash((self.name, self.value))")
        return self.current_code

    @codegen()
    def get_enum_default_py_def(self, indent=4, level=0):
        """Generate function which return default value for enum"""
        self.code("@staticmethod")
        self.code("def default():")
        self.indent()
        self.code("return %s.%s" % (self.get_class_name(),
                                    self.get_lowest_enum().name.upper()))
        return self.current_code

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

    def __init__(self, defs, indent, h_gen, h_dest, py_gen, py_dest, filename_prefix):
        self.defs = defs
        self.indent = indent
        self.h_gen = h_gen
        self.h_dest = h_dest
        self.py_gen = py_gen
        self.py_dest = py_dest
        self.filename_prefix = filename_prefix

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
            assert msg_elt.id is not None, "Message %s must have an id field" % (msg_elt.name)
            self.messages.append(msg_elt)
        # Check unicity of messages names
        msg_names = [m.name for m in self.messages]
        dups = set([n for n in msg_names if msg_names.count(n) > 1])
        assert len(msg_names) == len(set(msg_names)), "found %s message(s) duplicated" % (', '.join(dups))

        # Check unicity of messages ids
        msg_ids = [m.id for m in self.messages if m.id is not None]
        dups = set([n for n in msg_ids if msg_ids.count(n) > 1])
        if len(msg_ids) != len(set(msg_ids)):
            assert_msg = ""
            print("dups: %s" % (dups))
            for d in dups:
                dup_names = list()
                for m in self.messages:
                    if m.id == d:
                        dup_names.append(m.name)
                assert_msg += "id %s duplicated between %s\n" % (d, dup_names)

            assert len(msg_ids) == len(set(msg_ids)), "%s" % (assert_msg)

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
                    h_fd.write(e.get_enum_c_def(self.indent, 0))

                # Write Bitfield C definitions
                for bf in self.bitfields:
                    h_fd.write(bf.get_bitfield_c_defines(self.indent, 0))
                    h_fd.write(bf.get_bitfield_c_struct(self.indent, 0))

                # Write Messages C definitions
                for m in self.messages:
                    h_fd.write(m.get_define_msg_id_def(self.indent, 0))
                    h_fd.write(m.get_struct_c_def(self.indent, 0))

                # Finish file with footer
                h_fd.write(self.get_h_footer())

        if self.py_gen:
            py_file = self.py_dest + "/" + self.filename_prefix + ".py"
            with open(py_file, 'w') as py_fd:
                py_fd.write(self.get_py_header())

                # Write Enums python definitions
                for e in self.enums:
                    py_fd.write(e.get_enum_py_def(self.indent, 0))

                for bf in self.bitfields:
                    py_fd.write(bf.get_class_py_def(self.indent, 0))

                # Write Messages python definitions
                for m in self.messages:
                    py_fd.write(m.get_class_py_def(self.indent, 0))

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
    parser.add_argument("--py-name", type=str, default=None,
                        help="Python filename's suffix (without .py extention)")
    args = parser.parse_args()

    msg_file = open(args.yaml_file)
    messages = yaml.safe_load(msg_file)

    if args.py_name is None:
        args.py_name = os.path.splitext(args.yaml_file)[0]
    defs_gen = DefsGen(messages, args.indent,
                       args.h_gen, args.h_dest,
                       args.py_gen, args.py_dest, args.py_name)
    defs_gen.process_defs()


if __name__ == "__main__":
    main()
