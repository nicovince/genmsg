# Genmsg

Message generator for C and python with serialization/deserialization. The messages are defined in a yaml file, and allows the user to define messages, enumeration, bitfields, reusable types in messages.

The generated C header contains the structure for each message, defines for message ids and bitfields.

The generated python files contains classes for each message with serialization/deserialization methods, many _dunder_ methods to facilitate manipulation of the messages such as:
- `__str__`
- `__repr__`
- `__hash__`
- `__eq__`
- ...

Many assertions are generated to check input is correct.

## Installation
Download `genmsg.py` and give it execution rights, or clone this repository.

## Dependencies
This script uses `python3` and yaml processing. On Ubuntu the following package are required:

- python3
- python3-ruamel.yaml

```
sudo apt-get install python3 python3-ruamel.yaml
```

# Usage
```
./genmsg.py <yaml file> --h-gen --py-gen
```
This command will generate C header and python classes for handling the messages

Use `--help` to get additionnal help for the various options.

# Concepts and YAML syntax
Keep the names and id unique.

## Types
A `types` entry allows to define a composite type. Each entry must have a `name`, a `desc` and a `fields` list.

## Messages
A `messages` entry defines the list of available messages. Each entry must have a `name`, a numeric `id`, a `desc` and a `fields` list.

## Fields
A `fields` entry in a `messages` or `types` entry defines the various fields of a message or a type. Each field must have a `name`, a `description` and a `type`.

### type
A `type` in a `fields` list can be one of:
- `int8_t`
- `uint8_t`
- `int16_t`
- `uint16_t`
- `int32_t`
- `uint32_t`

When defining the type of a field's message, it can be a previously defined type's `name` in addition to one of the types mentionned above.

## Bitfields
A `bitfields` entry defines a list of bitfield, each entry must have a `name`, a `desc` and a list of `bits`

### Bits
A `bits` entry defines a list of fields in a bitfield, each entry must have a `name`, a `desc`, a `position` and a `width` (if greater than one).

## Enumeration
`enums` are used to define enumerations, each entry must have a `name`, a `desc` and a list of `entries` for each enum.

Each `entry` of the enumeration must have a `name`, a `value` and a `desc`

An `enum` can be added to a `bits` entry, or a `fields` entry.

# YAML Example
[test/example.yaml](test/example.yaml) uses all the features supported by `genmsg`
