# Pinned browser runtime: notices and corresponding source

MacroLab distributes the following runtime assets without modifying their upstream bytes. The exact asset checksums remain in `runtime/assets.lock.json`. The separate MacroLab Python wheel contains MacroLab code under its own MIT licence. No upstream runtime version was upgraded for this notice update.

## Pyodide 314.0.7

- Full Mozilla Public License 2.0 text: `Pyodide-314.0.7/LICENSE`.
- Exact corresponding upstream source: https://github.com/pyodide/pyodide/tree/b1e4fcc2488962f6360a97f19b9982d6fdb5d16f
- Downloadable source archive: https://github.com/pyodide/pyodide/archive/b1e4fcc2488962f6360a97f19b9982d6fdb5d16f.tar.gz
- Browser Python build configuration and patches: https://github.com/pyodide/pyodide/tree/b1e4fcc2488962f6360a97f19b9982d6fdb5d16f/cpython

The official `314.0.7` tag resolves to this commit. The official npm package metadata reports the same `gitHead`, and its integrity matches MacroLab's pinned npm runtime archive. The pinned source remains available under its upstream licence, including the MPL-covered files. MacroLab imposes no additional restriction on those source rights. The notice bundle records source links; it does not contain a second source archive or claim an independent reproducible build of the upstream WebAssembly binary.

## CPython 3.14.2

- Full Python licence history and terms: `CPython-3.14.2/LICENSE`.
- Complete upstream incorporated-software acknowledgements: `CPython-3.14.2/Doc/license.rst`.
- Exact upstream source: https://github.com/python/cpython/tree/df793163d5821791d4e7caf88885a2c11a107986
- Downloadable source archive: https://github.com/python/cpython/archive/df793163d5821791d4e7caf88885a2c11a107986.tar.gz

The official `v3.14.2` tag resolves to this commit, and 3.14.2 is the Python version declared by the pinned Pyodide runtime lock. The complete upstream acknowledgements are retained conservatively, including components not necessarily compiled into the WebAssembly runtime. The browser build's changes and build configuration are available in the pinned Pyodide source above. MacroLab makes no further changes to the upstream runtime or standard-library archive.

## Other shipped software

JavaScript and font notices are listed separately in `licences/manifest.json`. The nine scientific Python wheels are distributed unchanged with their embedded notices. This file addresses the pinned Pyodide/CPython notice and source-access gap; it is not a declaration that every optional upstream component is shipped or an independent legal opinion. No publication is approved by this notice bundle.
