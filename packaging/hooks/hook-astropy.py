"""Replacement for the contributed astropy hook.

Same collection as upstream, minus the plotting helpers: the contributed hook
walks astropy.visualization.wcsaxes, which aborts the build when matplotlib is
not installed. astropy resolves many modules and its ply parse tables at run
time, so everything else is collected as upstream does.
"""

from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata

_SKIP = ("astropy.visualization", "astropy.samp")


def _wanted(name: str) -> bool:
    return not name.startswith(_SKIP)


hiddenimports = [*collect_submodules("astropy", filter=_wanted), "numpy.lib.recfunctions"]

datas = collect_data_files("astropy")
datas += [
    (source, target)
    for source, target in collect_data_files("astropy", include_py_files=True)
    if source.endswith(("_parsetab.py", "_lextab.py"))
]
datas += copy_metadata("astropy")
datas += copy_metadata("numpy")
