#!/usr/bin/env python3
import re
import json

class MessageElt(object):
    """Message object created from json file"""
    def __init__(self, message):
        self.message = message
        self.check_message()

    def get_struct_c_def(self, indent=4, level=0):
        """Return string with C struct declaration properly indented"""
        indent_prefix = level*indent*" "
        out = "/* %s */\n" % (self.message["desc"])
        out += "typedef struct {\n"
        for f in self.message["fields"]:
            out += "%s%s %s; /* %s */\n" % (indent*" ", f["type"], f["name"], f["desc"])
        out += "} %s_t;" % (self.message["name"])
        out = re.sub("(^|\n)", r"\1" + indent_prefix, out)
        return out

    def check_message(self):
        """Verify message has unique field names"""
        # Check names duplicates
        names = [e["name"] for e in self.message["fields"]]
        if len(names) != len(set(names)):
            dups = set([ n for n in names if names.count(n) > 1 ])
            raise ValueError("found %s duplicated in %s" % (''.join(dups), self.message["name"]))

class EnumElt(object):
    """Enumeration object created from json file"""
    def __init__(self, enum):
        self.enum = enum
        self.check_enum()

    def get_enum_c_def(self, indent=4, level=0):
        """Return string with C enum declaration properly indented"""
        indent_prefix = level*indent*" "
        out = "/* %s */\n" % (self.enum["desc"])
        out += "typedef enum %s_e {\n" % (self.enum["name"])
        max_enum_val = 0
        for e in self.enum["entries"]:
            out += "%s%s = %d, /* %s */\n" % (indent*" ", e["entry"], e["value"], e["desc"])
            max_enum_val = max(max_enum_val, e["value"])
        out += "%s%s_END = %d\n" % (indent*" ", self.enum["name"], max_enum_val+1)
        out += "} %s_t;" % (self.enum["name"])
        out = re.sub("(^|\n)", r"\1" + indent_prefix, out)
        return out

    def get_enum_py_def(self, indent=4, level=0):
        """Return string with python enum declaration properly indented"""
        indent_prefix = level*indent*" "
        out = "# %s\n" % (self.enum["desc"])
        out += "class %s(Enum):\n" % (self.enum["name"])
        max_enum_val = 0
        for e in self.enum["entries"]:
            out += "%s%s = %d, # %s\n" % (indent*" ", e["entry"], e["value"], e["desc"])
            max_enum_val = max(max_enum_val, e["value"])
        out = re.sub("(^|\n)", r"\1" + indent_prefix, out)
        return out

    def check_enum(self):
        """Verify enum has only one instance of each name and value"""
        # Check names duplicates
        names = [e["entry"] for e in self.enum["entries"]]
        if len(names) != len(set(names)):
            dups = set([ n for n in names if names.count(n) > 1 ])
            raise ValueError("found %s duplicated in %s" % (''.join(dups), self.enum["name"]))
        # Check values duplicates
        vals = [e["value"] for e in self.enum["entries"]]
        if len(vals) != len(set(vals)):
            dups = set([ str(n) for n in vals if vals.count(n) > 1 ])
            raise ValueError("found value %s used for more than one name in %s" % (' '.join(dups), self.enum["name"]))



def main():
    msg_file = open("messages.json")
    messages = json.load(msg_file)
    for m in messages["messages"]:
        msg_elt = MessageElt(m)
        print(msg_elt.get_struct_c_def(4))
    for e in messages["enums"]:
        enum_elt = EnumElt(e)
        print(enum_elt.get_enum_c_def(3,1))
        print(enum_elt.get_enum_py_def(3,1))


if __name__ == "__main__":
    main()
