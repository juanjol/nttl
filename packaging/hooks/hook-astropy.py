"""Replacement for the contributed astropy hook.

Same collection as upstream, minus the plotting helpers. astropy.visualization
and astropy.samp abort the build when matplotlib is absent: the contributed
hook walks them when collecting submodules, and on Windows PyInstaller also
imports every collected package while searching for DLL dependencies, so their
data files have to stay out as well. astropy resolves many modules and its ply
parse tables at run time, so everything else is collected as upstream does.
"""

from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata

_SKIP = ("astropy.visualization", "astropy.samp")


def _wanted(name: str) -> bool:
    return not name.startswith(_SKIP)


hiddenimports = [*collect_submodules("astropy", filter=_wanted), "numpy.lib.recfunctions"]

_SKIP_PATHS = tuple(package.replace(".", "/") for package in _SKIP)


def _wanted_data(target: str) -> bool:
    return not target.replace("\\", "/").startswith(_SKIP_PATHS)


datas = [entry for entry in collect_data_files("astropy") if _wanted_data(entry[1])]
datas += [
    (source, target)
    for source, target in collect_data_files("astropy", include_py_files=True)
    if source.endswith(("_parsetab.py", "_lextab.py")) and _wanted_data(target)
]
datas += copy_metadata("astropy")
datas += copy_metadata("numpy")
