from std.python import Python, PythonObject
from std.python.bindings import PythonModuleBuilder
from std.os import abort


def abi_version() -> PythonObject:
    return Python.int(1)


def parity_approved() -> PythonObject:
    # This boundary module is deliberately inactive until the packed trie
    # implementation returns exact row-for-row parity on the committed corpus.
    return Python.bool(False)


@export
def PyInit__mojo_nlp() abi("C") -> PythonObject:
    try:
        var module = PythonModuleBuilder("_mojo_nlp")
        module.def_function[abi_version]("abi_version")
        module.def_function[parity_approved]("parity_approved")
        return module.finalize()
    except error:
        abort(String("error creating SectorTrace Mojo NLP module: ", error))
