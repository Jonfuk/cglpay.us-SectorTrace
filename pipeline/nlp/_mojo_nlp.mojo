from std.python import Python, PythonObject
from std.python.bindings import PythonModuleBuilder
from std.collections import List
from std.os import abort


def abi_version() raises -> PythonObject:
    return Python.int(1)


def parity_approved() raises -> PythonObject:
    # The packed ontology matcher is approved by scripts/build_mojo_nlp.py's
    # fixture-wide row-for-row parity check. Context remains Python-owned until
    # it has a separate packed ABI and the same exact proof.
    var builtins = Python.import_module("builtins")
    return builtins.bool(Python.int(1))


def _normalise(text: String) raises -> List[String]:
    """Match the ASCII surface of ontology._normalise before token scanning."""
    var value = text.lower()
    # The ontology aliases are ASCII.  Replacing every ASCII punctuation byte
    # keeps punctuation from joining neighbouring tokens while leaving the
    # authoritative Python loader responsible for the vocabulary itself.
    var punctuation: List[String] = [
        "!", "\"", "#", "$", "%", "&", "'", "(", ")", "*", "+", ",",
        "-", ".", "/", ":", ";", "<", "=", ">", "?", "@", "[", "\\",
        "]", "^", "`", "{", "|", "}", "~",
    ]
    for mark in punctuation:
        value = value.replace(mark, " ")
    var raw = value.split()
    var tokens = List[String](capacity=len(raw))
    for token in raw:
        var word = String(token)
        if word == "limited" or word == "ltd" or word == "llp" or word == "plc" or word == "cic":
            continue
        if word.byte_length() > 3 and word.endswith("s") and not word.endswith("ss"):
            word.resize(word.byte_length() - 1)
        tokens.append(word)
    return tokens^


def match_ontology(utf8: PythonObject, offsets: PythonObject,
                   _version: PythonObject, packed_trie: PythonObject) raises -> PythonObject:
    """Native token scan over the Python-owned, versioned packed alias rows."""
    var py_text = utf8.decode("utf-8")
    var source = String(py=py_text)
    var concept_column = Python.list()
    var start_column = Python.list()
    var end_column = Python.list()
    var count_column = Python.list()
    var ordinal_column = Python.list()
    var seen = List[String]()
    var text_count = len(offsets) - 1

    for text_ordinal in range(text_count):
        var byte_start = Int(py=offsets[text_ordinal])
        var byte_end = Int(py=offsets[text_ordinal + 1])
        var tokens = _normalise(String(source[byte=byte_start:byte_end]))
        var token_count = len(tokens)
        for start in range(token_count):
            var remaining = token_count - start
            var max_width = 8 if remaining > 8 else remaining
            for width in range(1, max_width + 1):
                for alias_index in range(len(packed_trie)):
                    var alias_row = packed_trie[alias_index]
                    var concept_ordinal = Int(py=alias_row[0])
                    var alias_tokens = String(py=alias_row[1]).split()
                    if len(alias_tokens) != width:
                        continue
                    var matches = True
                    for alias_token_index in range(width):
                        if String(alias_tokens[alias_token_index]) != tokens[start + alias_token_index]:
                            matches = False
                            break
                    if not matches:
                        continue
                    var key = String(text_ordinal, ":", concept_ordinal, ":", start, ":", start + width)
                    if key in seen:
                        continue
                    seen.append(key)
                    concept_column.append(Python.int(concept_ordinal))
                    start_column.append(Python.int(start))
                    end_column.append(Python.int(start + width))
                    count_column.append(Python.int(1))
                    ordinal_column.append(Python.int(text_ordinal))

    var builtins = Python.import_module("builtins")
    return builtins.tuple(Python.list(
        concept_column, start_column, end_column, count_column, ordinal_column))


@export
def PyInit__mojo_nlp() abi("C") -> PythonObject:
    try:
        var module = PythonModuleBuilder("_mojo_nlp")
        module.def_function[abi_version]("abi_version")
        module.def_function[parity_approved]("parity_approved")
        module.def_function[match_ontology]("match_ontology")
        return module.finalize()
    except error:
        abort(String("error creating SectorTrace Mojo NLP module: ", error))
