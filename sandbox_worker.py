
import sys
import io
import json


_SAFE_BUILTINS = {
    "print": print,
    "range": range,
    "len": len,
    "abs": abs,
    "min": min,
    "max": max,
    "sum": sum,
    "round": round,
    "sorted": sorted,
    "enumerate": enumerate,
    "zip": zip,
    "int": int,
    "float": float,
    "str": str,
    "bool": bool,
    "list": list,
    "dict": dict,
    "tuple": tuple,
    "set": set,
    "map": map,
    "filter": filter,
    "pow": pow,
    "True": True,
    "False": False,
    "None": None,
}

_ALLOWED_IMPORTS = {
    "math",
    "statistics",
    "random",
    "datetime",
    "decimal",
    "fractions",
    "itertools",
    "numpy",
    "scipy",
}


def _restricted_import(
    name,
    globals=None,
    locals=None,
    fromlist=(),
    level=0
):
    root = name.split(".")[0]

    if root not in _ALLOWED_IMPORTS:
        raise ImportError(
            f"Import of '{name}' is not permitted in the calculation sandbox."
        )

    return __import__(name, globals, locals, fromlist, level)


_SAFE_BUILTINS["__import__"] = _restricted_import


def main():
    code = sys.stdin.read()

    buffer = io.StringIO()
    old_stdout = sys.stdout
    sys.stdout = buffer

    result = {
        "success": False,
        "output": "NO_OUTPUT_ERROR: Code executed but printed no results."
    }

    try:
        exec(
            code,
            {"__builtins__": _SAFE_BUILTINS},
            {}
        )

        output = buffer.getvalue().strip()

        if output:
            result = {
                "success": True,
                "output": output
            }

    except Exception as e:
        result = {
            "success": False,
            "output": f"{type(e).__name__}: {str(e)}"
        }

    finally:
        sys.stdout = old_stdout

    print(json.dumps(result))


if __name__ == "__main__":
    main()

